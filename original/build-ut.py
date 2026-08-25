# -*- coding: utf-8 -*-
"""
UT용 멀티페이지 빌드.

Maze 는 '페이지 로드 시 URL 이 바뀔 때'만 경로 스텝을 기록한다. 문서가 요구하는 건
traditional multi-page site 이고, 한 파일 안에서 클래스만 토글하거나 쿼리 파라미터만
바꾸는 방식(= 모든 주소가 같은 HTML)은 잡히지 않는다.

그래서 index-mono.html 하나를 원본으로 두고, 화면마다 별도 .html 파일을 찍어낸다.
- 화면 전환은 전부 진짜 <a href> 링크 (JS 이동 없음)
- 각 파일은 자기 화면/탭만 활성화된 채로 나온다
- Maze 스니펫은 모든 파일에 그대로 들어간다

    python3 original/build-ut.py

index-mono.html 을 고칠 때마다 다시 돌리면 된다.
"""
import io, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'index-mono.html')
OUT = os.path.join(HERE, 'ut')

# 파일명 -> (화면, 패널 속성, 패널 값)
PAGES = {
    'detail':       ('detail',  'data-pane',  'info'),
    'detail-rev':   ('detail',  'data-pane',  'rev'),
    'results':      ('results', 'data-spane', 'all'),
    'results-shop': ('results', 'data-spane', 'shop'),
    'results-prod': ('results', 'data-spane', 'prod'),
    'results-rev':  ('results', 'data-spane', 'rev'),
    'ing':          ('ing',     'data-ipane', 'comp'),
    'ing-purp':     ('ing',     'data-ipane', 'purp'),
    'ing-skin':     ('ing',     'data-ipane', 'skin'),
}

TABS = {
    '.dtab': [('info', '상품정보', 'detail'), ('rev', '리뷰/성분', 'detail-rev')],
    '.stab': [('all', '전체', 'results'), ('shop', '쇼핑상품', 'results-shop'),
              ('prod', '제품', 'results-prod'), ('rev', '리뷰', 'results-rev')],
    '.itab': [('comp', '성분 구성', 'ing'), ('purp', '목적별', 'ing-purp'),
              ('skin', '피부 타입별', 'ing-skin')],
}
TAB_ATTR = {'.dtab': 'data-pane', '.stab': 'data-spane', '.itab': 'data-ipane'}
# 탭 그룹이 속한 화면. 'rev' 처럼 키가 겹치므로 자기 화면일 때만 선택 표시한다.
TAB_SCREEN = {'.dtab': 'detail', '.stab': 'results', '.itab': 'ing'}

ANCHOR_CSS = u"""
/* ---------- 링크 내비게이션 (Maze 경로 추적) ----------
   화면 전환을 전부 <a href> 로 바꿨다. 버튼이던 시절의 모양을 그대로 유지한다. */
a.dtab,a.itab,a.stab,a.iconbtn,a.scard,a.prodrow,a.shopcard,a.rvprod,a.subhead,.fsfoot a{text-decoration:none;color:inherit;}
a.dtab,a.itab{display:block;text-align:center;}
a.stab{display:inline-block;}
.fsfoot a{display:block;text-align:center;border:1px solid var(--line2);background:var(--bg);border-radius:9px;padding:14px 0;font-size:14px;font-weight:600;cursor:pointer;letter-spacing:-.03em;}

"""


def strip_router(s):
    """?s= 라우터(head 스크립트 + CSS + JS)를 걷어낸다. 이제 링크가 그 일을 한다."""
    s, n = re.subn(r'<!-- URL 라우팅 \(Maze 경로 추적용\).*?</script>\n', '', s, flags=re.S)
    assert n == 1, 'head 라우터 스크립트를 못 찾음'
    s, n = re.subn(r'/\* -{10} URL 라우팅 \(\?s=\) -{10}.*?display:block;\}\n\n', '', s, flags=re.S)
    assert n == 1, '라우팅 CSS 를 못 찾음'
    return s


def strip_nav_js(s):
    """JS 화면전환 로직 제거 — 이동은 전부 브라우저가 한다."""
    cuts = [
        r'  /\* 화면 전환 = 진짜 페이지 이동.*?\n  \}\)\(\);\n',           # show() + 부팅 블록
        r"    if\(\(t = e\.target\.closest\('\.dtab'\)\)\)\{.*?\n    \}\n",
        r"    if\(\(t = e\.target\.closest\('\[data-go-ing\]'\)\)\)\{[^\n]*\n",
        r"    if\(\(t = e\.target\.closest\('\[data-go-detail\]'\)\)\)\{[^\n]*\n",
        r"    if\(\(t = e\.target\.closest\('\.itab'\)\)\)\{.*?\n    \}\n",
        r"    if\(\(t = e\.target\.closest\('\.stab'\)\)\)\{.*?\n    \}\n",
        r"    if\(\(t = e\.target\.closest\('\[data-go-results\]'\)\)\)\{[^\n]*\n",
    ]
    for c in cuts:
        s, n = re.subn(c, '', s, flags=re.S)
        assert n == 1, 'JS 제거 실패: ' + c[:44]
    # 궁합 시트의 '성분' 버튼은 링크가 됐으니 JS 이동만 뺀다
    s = s.replace("      if(t.dataset.fitsheet === 'ing'){ show('ing'); }\n", '')
    return s


def to_anchor(s, marker, href, count):
    """<button ... marker ...>…</button> 를 같은 속성의 <a href> 로 바꾼다."""
    pat = re.compile(r'<button([^>]*?' + re.escape(marker) + r'[^>]*?)>(.*?)</button>', re.S)
    s, n = pat.subn(lambda m: '<a' + m.group(1) + ' href="' + href + '">' + m.group(2) + '</a>', s)
    assert n == count, '%s : %d 개 기대, %d 개 변환' % (marker, count, n)
    return s


def build(name):
    screen, pane_attr, pane_val = PAGES[name]
    s = io.open(SRC, encoding='utf-8').read()
    s = strip_router(s)
    s = strip_nav_js(s)

    # 앵커용 CSS
    s = s.replace('/* ===== 목업 없음 : 앱 화면만.', ANCHOR_CSS + '/* ===== 목업 없음 : 앱 화면만.')

    # 탭 -> 링크 (선택 상태는 이 파일 기준으로 고정)
    for sel_key, items in TABS.items():
        cls, attr = sel_key[1:], TAB_ATTR[sel_key]
        for key, label, target in items:
            old = '<button class="%s" role="tab" aria-selected="%s" %s="%s">%s</button>'
            sel = (key == pane_val and TAB_SCREEN[sel_key] == screen)
            new = '<a class="%s" role="tab" aria-selected="%s" %s="%s" href="%s.html">%s</a>' % (
                cls, 'true' if sel else 'false', attr, key, target, label)
            hit = None
            for was in ('true', 'false'):
                cand = old % (cls, was, attr, key, label)
                if cand in s:
                    hit = cand
                    break
            assert hit, '탭 마크업 못 찾음: %s %s' % (cls, key)
            s = s.replace(hit, new)

    # 나머지 내비게이션 -> 링크
    s = to_anchor(s, 'data-go-results', 'results.html', 1)
    s = to_anchor(s, 'data-go-ing', 'ing.html', 4)          # inglink 1 + subhead 3
    s = to_anchor(s, 'data-go-detail', 'detail.html', 29)   # 뒤로 1 + 카드/행 28
    s = to_anchor(s, 'data-fitsheet="ing"', 'ing.html', 1)

    # 활성 화면 / 패널
    s = s.replace('<section class="screen is-active"', '<section class="screen"')
    a = '<section class="screen" data-screen="%s">' % screen
    assert s.count(a) == 1, '화면 못 찾음: ' + screen
    s = s.replace(a, '<section class="screen is-active" data-screen="%s">' % screen)

    s = s.replace('class="pane is-active"', 'class="pane"')
    a = '<div class="pane" %s="%s">' % (pane_attr, pane_val)
    assert s.count(a) == 1, '패널 못 찾음: %s=%s' % (pane_attr, pane_val)
    s = s.replace(a, '<div class="pane is-active" %s="%s">' % (pane_attr, pane_val))

    # 남은 JS 이동 흔적이 없어야 한다
    assert 'location.assign' not in s, name + ' : location.assign 잔존'
    assert ':root[data-scr' not in s and 'setAttribute(\'data-scr\'' not in s, name + ' : 라우터 잔존'

    io.open(os.path.join(OUT, name + '.html'), 'w', encoding='utf-8').write(s)
    return len(s)


if not os.path.isdir(OUT):
    os.makedirs(OUT)
for name in PAGES:
    n = build(name)
    print('  ut/%-18s %d chars' % (name + '.html', n))

# 디렉터리 URL(.../ut/)로도 열리도록 시작 화면을 index.html 로도 둔다
import shutil
shutil.copyfile(os.path.join(OUT, 'detail.html'), os.path.join(OUT, 'index.html'))
print('  ut/index.html        (detail.html 복사)')
print('%d개 파일 생성 완료' % (len(PAGES) + 1))
