"""Editable document identity, with defaults transcribed from the source exams."""
import re

SOURCE_FOOTERS = {
    'exam-1': ('29 de Oct 2018, Rev. 00', 'FO-RH-13'),
    'exam-2': ('09/07/2025, Rev. 01', 'FO-RH-14'),
    'exam-3': ('30 de Mayo del 2025, Rev. 02', 'FO-RH-14'),
    'exam-4': ('29 de Oct 2018, Rev. 00', 'FO-RH-01'),
    'exam-5': ('29 de Oct 2018, Rev. 00', 'FO-RH-13'),
}
LIMITS = {'top_text': 180, 'revision_text': 120, 'footer_left': 240, 'footer_center': 180, 'footer_right': 100}
REFERENCE_FOOTER = ('09/07/2025, Rev. 01', 'FO-RH-14')


def document_settings(exam):
    revision = re.search(r'Rev\.\s*(\d+)', exam.get('revision', ''), re.I)
    footer, code = SOURCE_FOOTERS.get(exam.get('id'), REFERENCE_FOOTER)
    defaults = {
        'top_text': 'EVALUACIÓN DE COMPRENSIÓN',
        'revision_text': 'Rev. de Evaluación: ' + (revision.group(1) if revision else '00'),
        'footer_left': 'Fecha de Elaboración ' + footer if footer else '',
        'footer_center': 'Manufacturas Especializadas S.A.',
        'footer_right': code,
    }
    custom = exam.get('document', {})
    if not isinstance(custom, dict):
        raise ValueError('El encabezado y pie de página deben contener campos de texto.')
    for key, limit in LIMITS.items():
        value = custom.get(key, defaults[key])
        if not isinstance(value, str) or len(value) > limit or any(ord(c) < 32 and c not in '\n\r\t' for c in value):
            raise ValueError(f'Texto de documento inválido: {key} (máximo {limit} caracteres).')
        defaults[key] = value.strip() or (defaults[key] if key in ('footer_left','footer_right') else '')
    return defaults
