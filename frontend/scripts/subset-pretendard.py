"""
Pretendard 가변 글꼴(app/fonts/PretendardVariable.woff2, 약 2MB)을 글자 묶음별 작은 파일로 나눈다.

브라우저는 @font-face의 unicode-range를 보고 화면에 실제로 쓰인 글자가 든 파일만 받는다.
그래서 랜딩 첫 화면은 latin + hero 두 파일(약 60KB)만으로 그릴 수 있고,
나머지 묶음은 그 글자가 필요한 화면에서만 내려받는다.

  latin   영문·숫자·문장부호와 소스에서 쓰는 기호
  hero    랜딩 헤더·히어로에 보이는 한글(HERO_TEXT)
  common  자주 쓰는 한글 2,350자(KS X 1001) + 소스에 나오는 한글 + 한글 자모
  etc     그 밖의 기호·외국 문자
  rare1~4 나머지 한글(주소·상호 등 드문 글자가 나올 때만 받는다)

실행(frontend 폴더에서):  pip install fonttools brotli && python3 scripts/subset-pretendard.py
결과: public/fonts/pretendard/*.woff2, app/fonts/pretendard.css, styles/fonts.ts
히어로·헤더 문구를 바꾸면 HERO_TEXT를 맞춰 고치고 다시 실행한다.
(빠진 글자가 있어도 common 묶음에서 그려지므로 깨지지는 않고, 첫 화면이 조금 늦어질 뿐이다.)
"""

import hashlib
import os
import re
import subprocess
import tempfile

from fontTools.ttLib import TTFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'app/fonts/PretendardVariable.woff2')
OUT_DIR = os.path.join(ROOT, 'public/fonts/pretendard')
URL_DIR = '/fonts/pretendard'

# 랜딩 헤더와 히어로(.landing-hero)에 보이는 한글 — 화면 글자를 그대로 모은 것
HERO_TEXT = (
    '가간건검경곳공관교구권균기내는다대데도동드려로료루를리맞먼명미반변보분비상새석소시실알어업에예올와요'
    '용우운움원유육을음이인임있작장저적점조종주채천추치카코터토트페평포하학합해홈'
)

# 영문·숫자·문장부호 + 소스에서 쓰는 기호(₩ ※ → ≤ ① ─ ▲ ▼ ○ ㎡ 등)
LATIN_RANGES = [
    (0x0000, 0x00FF), (0x2010, 0x2027), (0x2030, 0x203B), (0x20A9, 0x20A9), (0x20AC, 0x20AC),
    (0x2122, 0x2122), (0x2190, 0x2194), (0x2212, 0x2212), (0x2264, 0x2265), (0x2460, 0x2473),
    (0x2500, 0x2500), (0x25B2, 0x25B2), (0x25BC, 0x25BC), (0x25CB, 0x25CB), (0x33A1, 0x33A1),
    (0x3000, 0x3011),
]


def is_hangul(u):
    return 0xAC00 <= u <= 0xD7A3


def source_hangul():
    found = set()
    for top in ('app', 'components', 'lib', 'styles'):
        for root, dirs, files in os.walk(os.path.join(ROOT, top)):
            for name in files:
                if name.endswith(('.ts', '.tsx', '.css')):
                    with open(os.path.join(root, name), encoding='utf-8') as f:
                        found |= {ord(c) for c in re.findall('[가-힣]', f.read())}
    return found


def ksx1001_hangul():
    found = set()
    for hi in range(0xB0, 0xC9):
        for lo in range(0xA1, 0xFF):
            try:
                found.add(ord(bytes([hi, lo]).decode('euc-kr')))
            except UnicodeDecodeError:
                pass
    return {u for u in found if is_hangul(u)}


def unicode_range(codes):
    codes = sorted(codes)
    parts, i = [], 0
    while i < len(codes):
        j = i
        while j + 1 < len(codes) and codes[j + 1] == codes[j] + 1:
            j += 1
        parts.append(f'U+{codes[i]:X}' if i == j else f'U+{codes[i]:X}-{codes[j]:X}')
        i = j + 1
    return ', '.join(parts)


def main():
    cmap = set(TTFont(SRC).getBestCmap())
    hero = {ord(c) for c in HERO_TEXT} & cmap
    latin = {u for u in cmap if any(a <= u <= b for a, b in LATIN_RANGES)}
    common = ((ksx1001_hangul() | source_hangul()) & cmap) - hero
    common |= {u for u in cmap if 0x3131 <= u <= 0x318E}
    etc = {u for u in cmap if not is_hangul(u)} - latin - common
    rare = sorted({u for u in cmap if is_hangul(u)} - hero - common)
    chunks = {'latin': latin, 'hero': hero, 'common': common, 'etc': etc}
    for i in range(4):
        chunks[f'rare{i + 1}'] = set(rare[i * len(rare) // 4:(i + 1) * len(rare) // 4])

    os.makedirs(OUT_DIR, exist_ok=True)
    for old in os.listdir(OUT_DIR):
        if old.endswith('.woff2'):
            os.remove(os.path.join(OUT_DIR, old))

    urls, faces = {}, []
    with tempfile.TemporaryDirectory() as tmp:
        for name, codes in chunks.items():
            codes_file = os.path.join(tmp, 'codes.txt')
            out = os.path.join(tmp, f'{name}.woff2')
            with open(codes_file, 'w') as f:
                f.write(','.join(f'{u:X}' for u in sorted(codes)))
            subprocess.run(
                ['pyftsubset', SRC, f'--unicodes-file={codes_file}', '--layout-features+=tnum',
                 '--flavor=woff2', f'--output-file={out}'],
                check=True,
            )
            data = open(out, 'rb').read()
            # 내용이 바뀌면 파일 이름도 바뀌게 해서 오래 캐시해도 안전하다(next.config.ts 참고)
            file = f'pretendard-{name}.{hashlib.sha256(data).hexdigest()[:8]}.woff2'
            open(os.path.join(OUT_DIR, file), 'wb').write(data)
            urls[name] = f'{URL_DIR}/{file}'
            faces.append(
                '@font-face {\n'
                "  font-family: 'pretendard';\n"
                f"  src: url('{urls[name]}') format('woff2');\n"
                '  font-weight: 45 920;\n'
                '  font-style: normal;\n'
                '  font-display: swap;\n'
                f'  unicode-range: {unicode_range(codes)};\n'
                '}'
            )
            print(f'{name:7s} {len(codes):5d}자 {len(data) // 1024:4d}KB')

    header = (
        '/* scripts/subset-pretendard.py가 만든 파일 — 직접 고치지 말고 스크립트를 다시 실행한다. */\n\n'
        ':root {\n'
        "  --font-pretendard: 'pretendard', 'pretendard Fallback';\n"
        '}\n\n'
        '/* 글꼴을 받기 전 잠깐 쓰는 Arial을 Pretendard 크기에 맞춰 둬서 글꼴이 바뀔 때 줄이 덜 밀린다. */\n'
        '@font-face {\n'
        "  font-family: 'pretendard Fallback';\n"
        '  src: local(Arial);\n'
        '  ascent-override: 93.76%;\n'
        '  descent-override: 23.75%;\n'
        '  line-gap-override: 0%;\n'
        '  size-adjust: 101.55%;\n'
        '}\n\n'
    )
    with open(os.path.join(ROOT, 'app/fonts/pretendard.css'), 'w') as f:
        f.write(header + '\n\n'.join(faces) + '\n')
    with open(os.path.join(ROOT, 'styles/fonts.ts'), 'w') as f:
        f.write(
            '// scripts/subset-pretendard.py가 만든 파일 — 직접 고치지 말고 스크립트를 다시 실행한다.\n'
            '// 첫 화면에 바로 필요한 Pretendard 묶음 주소(미리 받기용).\n'
            f"export const PRETENDARD_LATIN_URL = '{urls['latin']}';\n"
            f"export const PRETENDARD_HERO_URL = '{urls['hero']}';\n"
            '\n'
            '// 예전 next/font 객체와 같은 모양 — 컴포넌트의 `pretendard.className`이 그대로 동작한다.\n'
            "export const pretendard = { className: 'font-sans', variable: '' };\n"
        )


if __name__ == '__main__':
    main()
