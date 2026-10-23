"""Реже вопросы в ответах радара в чатах."""
import sys
p = sys.argv[1] if len(sys.argv) > 1 else '/opt/radar/radar.py'
s = open(p, encoding='utf-8').read()
s = s.replace('Иногда одно вопросительное предложение, чтобы втянуть в диалог.',
              'Вопрос редко, примерно в каждом третьем ответе. Чаще просто короткое мнение или факт.')
open(p, 'w', encoding='utf-8').write(s)
print('OK14')
