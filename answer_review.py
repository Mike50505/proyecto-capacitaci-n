"""Private answer-by-answer feedback using the submitted exam's answer key."""
import math
import unicodedata


def normalize(value):
    return ' '.join(unicodedata.normalize('NFKC', str(value)).casefold().split())


def question_review(question, answer, grade):
    points = grade.get('points')
    maximum = question['points']
    status = 'pending' if points is None else 'incorrect' if points <= 0 else 'correct' if points >= maximum - 0.00005 else 'partial'
    key, typ = question.get('correct'), question['type']
    has_key = key is not None and typ != 'image_mark'
    result = {'status': status, 'has_key': has_key, 'correct_answer': key if has_key else None, 'items': []}
    if not has_key:
        return result
    if typ in ('matching', 'table'):
        values = answer if isinstance(answer, dict) else {}
        for item_key, correct in key.items():
            if typ == 'matching':
                label = item_key
            else:
                row, column = map(int, item_key.split(':'))
                label = question['rows'][row] + ' / ' + question['columns'][column]
            value = values.get(item_key, '')
            result['items'].append({'key': item_key, 'label': label, 'answer': value, 'correct_answer': correct, 'correct': normalize(value) == normalize(correct)})
        result['matched'] = sum(item['correct'] for item in result['items'])
        result['total'] = len(result['items'])
    elif typ in ('single', 'multiple', 'boolean'):
        options = ['Verdadero', 'Falso'] if typ == 'boolean' else question['options']
        selected = set(answer or []) if typ == 'multiple' else {answer}
        correct_options = set(key) if typ == 'multiple' else {key}
        result['items'] = [{'label': option, 'selected': option in selected, 'correct': option in correct_options} for option in options]
    elif typ == 'number':
        try:
            value = float(answer)
            result['answer_correct'] = math.isfinite(value) and abs(value - float(key)) <= float(question.get('tolerance', 0))
        except (TypeError, ValueError):
            result['answer_correct'] = False
    else:
        result['answer_correct'] = normalize(answer if answer is not None else '') == normalize(key)
    return result


def answer_review(exam, answers, grading):
    return {q['id']: question_review(q, answers.get(q['id']), grading.get(q['id'], {})) for q in exam['questions']}
