import sys
p = sys.argv[1] if len(sys.argv) > 1 else '/opt/radar/radar.py'
s = open(p, encoding='utf-8').read()

# 1. «видимость»: на любой вопрос по нашим темам (виза, Emirates ID, счёт, компания) после оценки нейросетью
b = '''        res = await ask_llm(title, text)
'''
if 'autoreply.maybe_visibility' not in s:
    assert b in s, 'llm anchor'
    s = s.replace(b, b + '''        if res:
            asyncio.get_event_loop().create_task(autoreply.maybe_visibility(user, ev, sender, text, res))
''', 1)

# 2. фильтр до нейросети: визы и Emirates ID в любом написании
kw = 'emirates ?id|эмирейтс ?ай ?ди|эмирейтс|резидентск\\w* виз|рабоч\\w* виз|продлени\\w* виз|продлить виз|\\bвнж\\b|резидентств|ресидент|визу? на \\d|'
if 'emirates ?id' not in s and 'STRONG_RE = re.compile(r"' in s:
    s = s.replace('STRONG_RE = re.compile(r"', 'STRONG_RE = re.compile(r"' + kw, 1)

open(p, 'w', encoding='utf-8').write(s)
print('FIX19_OK', 'STRONG_RE' in s)
