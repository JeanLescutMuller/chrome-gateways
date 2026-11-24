"""Headless test of the "Agent tab notes" extension (agent-gateway/extension/) and its native host (agent-gateway/native_host.py),
against a temporary $CHROME_STATE, in a Chrome for Testing with a throwaway profile (branded Chrome ignores
--load-extension since version 137). Nothing touches the real record or a real Chrome profile.

Usage: <python with playwright 1.55> tests/test_extension.py <Chrome for Testing binary> <scratch dir> [<screenshots dir>]
  e.g. npx @puppeteer/browsers install chrome@stable --path <scratch>   # gets a Chrome for Testing
Reads: agent-gateway/extension/, agent-gateway/native_host.py and agent_chrome.py, shared/chrome_kit.py.
Writes: in <scratch dir>: state/ (the temporary record), profile/ (throwaway, with NativeMessagingHosts/), host.sh;
screenshots in <screenshots dir> (default <scratch dir>). Prints PASS/FAIL per check; terminates its Chrome.
"""
import http.server
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]   # the repo: agent-gateway/, script-gateway/, terminal-links/, shared/


def code(name: str) -> Path:
    """A module of the repo by its file name, in whichever folder it lives."""
    return next(ROOT / d / name for d in ('agent-gateway', 'script-gateway', 'terminal-links', 'shared') if (ROOT / d / name).exists())
EXT, EXT_ID, HOST = ROOT / 'agent-gateway/extension', 'hfnfcdbehfbggjaccimmnolmhdkbfdie', 'com.jeanlescut.agent_tab_notes'
SCRATCH = Path(sys.argv[2]).resolve()
SHOTS = Path(sys.argv[3]).resolve() if len(sys.argv) > 3 else SCRATCH
STATE = SCRATCH / 'state'
shutil.rmtree(STATE, ignore_errors=True)
os.environ['CHROME_STATE'] = str(STATE)
os.environ.pop('TMUX_PANE', None)
os.environ['CHROME_TEST_DESKTOP'] = ''   # authorize-tab: never the user's iTerm2
PS = SCRATCH / 'ps.txt'                     # the "user's Chrome", started an hour ago: tabs opened since then are shown
PS.write_text('  501 01:00:00 /Applications/Google Chrome.app/Contents/MacOS/Google Chrome\n')
os.environ['CHROME_TEST_PS'] = str(PS)
sys.path[:0] = [str(ROOT / 'agent-gateway'), str(ROOT / 'shared')]
import chrome_kit as kit  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

GEN = '331a94e7-f123-4e09-a755-cdc63980187f'
SID, SID2 = '3f2a9c1e-77b0-4d1e-9a51-0c0ffee12345', '7d41e2aa-1b9c-4c55-8e0f-2a6b9c3d4e5f'
PROJ = SCRATCH / 'job-applications'         # a "repo": its folder name is the project
(PROJ / '.git').mkdir(parents=True, exist_ok=True)
results = []

# "Covered": visible page elements that paint something (text, image, control, coloured box) under the bar
MEASURE = """() => {
  const H = parseFloat(getComputedStyle(document.documentElement).marginTop) || 28;   // push.js: html margin = the bar's height
  const bar = [...document.querySelectorAll('agent-tab-note')];
  const painted = e => {
    if (e === document.documentElement || e === document.body || bar.includes(e)) return false;
    const cs = getComputedStyle(e);
    if (cs.visibility !== 'visible' || +cs.opacity === 0 || cs.display === 'none') return false;
    if (/^(IMG|SVG|INPUT|BUTTON|TEXTAREA|SELECT|IFRAME|VIDEO|CANVAS)$/i.test(e.tagName)) return true;
    if ([...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())) return true;
    return cs.backgroundColor !== 'rgba(0, 0, 0, 0)' && cs.backgroundColor !== 'transparent';
  };
  return [...document.querySelectorAll('body *')].filter(painted).filter(e => { const r = e.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && r.top < H && r.bottom > 0; }).map(e => e.tagName).slice(0, 5);
}"""


def check(name, ok, detail=''):
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {str(detail)[:160]}", flush=True)


class Pages(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = ("<!doctype html><title>Fixed header page</title><body style='margin:0;font:16px sans-serif'>"
                "<header style='position:fixed;top:0;left:0;right:0;height:56px;background:#0a66c2;color:#fff;padding:12px;"
                f"box-sizing:border-box'>Fixed site header {self.path} (like LinkedIn logged in)</header>"
                "<main style='padding:72px 24px'><h1>A page with a fixed header</h1><p>Lorem ipsum.</p></main></body>").encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.send_header('Content-Security-Policy', "default-src 'none'; script-src 'none'; style-src 'unsafe-inline'")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def claim(*args, sid=SID):
    r = subprocess.run(['/usr/bin/python3', '-I', str(code('agent_chrome.py')), *args], cwd=PROJ, capture_output=True,
                       text=True, env={**os.environ, 'CLAUDE_CODE_SESSION_ID': sid})
    assert r.returncode == 0, r.stderr


def bar_text(page) -> str:
    """The bar's text, read through its closed shadow root (CDP DOM with pierce)."""
    cdp = page.context.new_cdp_session(page)
    root = cdp.send('DOM.getDocument', {'depth': -1, 'pierce': True})['root']
    out, stack, inside = [], [(root, False)], False
    while stack:
        n, inside = stack.pop()
        inside = inside or n.get('localName') == 'agent-tab-note'
        if inside and n.get('nodeType') == 3:
            out.append(n.get('nodeValue', ''))
        kids = n.get('children', []) + n.get('shadowRoots', [])
        stack += [(k, inside) for k in reversed(kids)]
    cdp.detach()
    return ''.join(out)


def bar_on_top(page) -> bool:
    return page.evaluate("document.elementFromPoint(innerWidth / 2, 8)?.tagName") == 'AGENT-TAB-NOTE'


DESKS = SCRATCH / 'desks.json'   # each window's desktop, as macOS would say (the host reads it: CHROME_TEST_DESKTOPS)


def windows(ctx, ctl, base):
    """7. One agent window per Claude account and desktop (extension/place.js): a session's tab group that lands in a
    window on another desktop moves to this profile's window on its session's desktop; no window there: it stays; the
    user's tabs never move. Desktops: window 1 and "the user's" on 100, window 2 on 200, nothing on 300."""
    js = ctl.evaluate
    sids = iter(['aaaa0000-0000-4000-8000-00000000000%d' % i for i in range(1, 9)])
    (SCRATCH / 'proj-a' / '.git').mkdir(parents=True, exist_ok=True)

    def agent_group(win, path):   # what Claude in Chrome does: an inactive tab, in its own group
        tab = js(f"chrome.tabs.create({{windowId: {win}, url: '{base}/{path}', active: false}}).then(t => t.id)")
        gid = js(f"chrome.tabs.group({{tabIds: [{tab}], createProperties: {{windowId: {win}}}}})")
        return tab, gid

    def rec(tab, url, desktop):   # the hook's record of the tab, with its session's desktop (authorize-tab's)
        kit.record([{'event': 'open', 'tab_id': tab, 'url': url, 'profile': 'Claude - Account A', 'device_id': GEN}],
                   {'session_id': next(sids), 'cwd': str(SCRATCH / 'proj-a'), 'desktop': desktop})

    tab_of = lambda t: js(f'chrome.tabs.get({t})')
    s_win = lambda: set(js("chrome.windows.getAll({windowTypes: ['normal']}).then(l => l.map(w => w.id))"))
    active = lambda w: js(f'chrome.tabs.query({{windowId: {w}, active: true}}).then(l => l[0].id)')

    def desks(d):   # macOS's answer changes: write it, then a window event makes the extension report again
        DESKS.write_text(json.dumps({str(k): v for k, v in d.items()}))
        w = js("chrome.windows.create({focused: false}).then(w => w.id)")
        js(f'chrome.windows.remove({w})')
        time.sleep(1.5)

    # 7a. open-profile-window's first tab names the profile; the host answers each window's desktop
    w1 = js(f"chrome.windows.create({{focused: false, url: 'chrome-extension://{EXT_ID}/window.html?profile=Claude+-+Account+A'}}).then(w => w.id)")
    w2 = js("chrome.windows.create({focused: false}).then(w => w.id)")
    w_u = js(f"chrome.windows.create({{focused: true, url: '{base}/user-page'}}).then(w => w.id)")
    d_desk = {w1: [100], w2: [200], w_u: [100]}
    desks(d_desk)
    d_rep = next((d for f in sorted((STATE / 'windows').glob('*.json')) if str(w2) in (d := kit.read_json(f)).get('desktops', {})), {})
    stored = js("chrome.storage.session.get('desk').then(r => r.desk || {})")
    check('7a. the window report names the profile and carries each window\'s desktop; the extension has them',
          d_rep.get('desktops', {}).get(str(w2), {}).get('desktops', [{}])[0].get('space') == 200
          and stored.get(str(w1)) == [100], (d_rep.get('desktops'), stored))

    # 7b. a session on desktop 200 lands in the user's window (desktop 100): its group moves to window 2
    t_user = active(w_u)
    t1, g1 = agent_group(w_u, 'a1')
    time.sleep(1)
    pg = next(x for x in ctx.pages if x.url.endswith('/a1'))   # a CDP session attached before the move (as Claude in Chrome's)
    rec(t1, f'{base}/a1', 200)
    time.sleep(2.5)
    t1i = tab_of(t1)
    check('7b. the group moved to the account\'s window on its session\'s desktop, same group id, not made active',
          t1i['windowId'] == w2 and t1i['groupId'] == g1 and not t1i['active'], t1i)
    check('7b. the user\'s tab and window untouched (still there, still active)',
          tab_of(t_user)['windowId'] == w_u and active(w_u) == t_user and w_u in s_win())
    try:
        title = pg.evaluate('document.title')
        pg.goto(f'{base}/a1-next')
        shot = len(pg.screenshot())
        ok = 'Fixed header' in title and tab_of(t1)['url'].endswith('/a1-next') and shot > 1000
    except Exception as e:  # noqa: BLE001
        ok, title = False, str(e)
    check('7b. after the move the same CDP session still reads, navigates and screenshots the tab', ok, title)

    # 7c. a session on desktop 300, where the account has no window: the tab stays where it landed
    s0 = s_win()
    t2, _ = agent_group(w1, 'a2')
    rec(t2, f'{base}/a2', 300)
    time.sleep(2.5)
    check('7c. no window of the account on its desktop: the tab stays (no window is created)', tab_of(t2)['windowId'] == w1
          and s_win() == s0, (s0, s_win()))

    # 7d. a window created by the group's arrival (unfocused, only a new tab): the group moves out, the window closes
    w_new = js("chrome.windows.create({focused: false}).then(w => w.id)")
    desks({**d_desk, w_new: [200]})
    t3, _ = agent_group(w_new, 'a3')
    rec(t3, f'{base}/a3', 100)
    time.sleep(2.5)
    check('7d. a window the arrival created: group moved to the desktop\'s window, the empty window closed',
          tab_of(t3)['windowId'] in (w1, w_u) and w_new not in s_win(), (tab_of(t3)['windowId'], s_win()))

    # 7e. a group holding a user's tab (not in open.json): never moved
    t4, g4 = agent_group(w_u, 'a4')
    t_mine = js(f"chrome.tabs.create({{windowId: {w_u}, url: '{base}/user-2', active: false}}).then(t => t.id)")
    js(f'chrome.tabs.group({{tabIds: [{t_mine}], groupId: {g4}}})')
    rec(t4, f'{base}/a4', 200)
    time.sleep(2.5)
    check('7e. a group with a user\'s tab in it stays where it is', tab_of(t4)['windowId'] == w_u and tab_of(t_mine)['windowId'] == w_u)
    log = js("chrome.storage.session.get('placeLog').then(r => r.placeLog || [])")
    print('      placeLog:', [(x.get('action'), x.get('desktop'), x.get('tab')) for x in log][-8:])


def expiry(ctx, ctl, base):
    """8. A tab kept for a human past its deadline: the extension closes it, the host records "expired" and leaves the
    session a notice (part C, 1 Nov 2026). The deadline is shortened with $CHROME_NEEDS_HUMAN_TTL (the marking process)."""
    sid = 'eeee0000-0000-4000-8000-000000000001'
    pg = ctx.new_page()
    pg.goto(f'{base}/login')
    tid = max(t['id'] for t in ctl.evaluate('chrome.tabs.query({})'))
    kit.record([{'event': 'open', 'tab_id': tid, 'url': f'{base}/login', 'profile': 'Claude - Account A', 'device_id': GEN}],
               {'session_id': sid, 'cwd': str(PROJ)})
    r = subprocess.run(['/usr/bin/python3', '-I', str(code('agent_chrome.py')), 'authorize-tab', '--mode', 'single', 'log in', '--visibility',
                        'unfocused', '--visibility-reason', 'a login', '--project', 'job-applications'], cwd=PROJ,
                       capture_output=True, text=True, env={**os.environ, 'CLAUDE_CODE_SESSION_ID': sid})
    r = subprocess.run(['/usr/bin/python3', '-I', str(code('agent_chrome.py')), 'mark-as-needing-human', 'log in'], cwd=PROJ,
                       capture_output=True, text=True, env={**os.environ, 'CLAUDE_CODE_SESSION_ID': sid, 'CHROME_NEEDS_HUMAN_TTL': '4'})
    t0 = time.time()
    while time.time() - t0 < 12 and str(tid) in kit.read_open():
        time.sleep(0.5)
    still = [t['id'] for t in ctl.evaluate('chrome.tabs.query({})') if t['id'] == tid]
    h = [json.loads(x) for f in sorted(kit.HISTORY.glob('*.jsonl')) for x in f.read_text().splitlines()]
    last = [x for x in h if x['tab_id'] == tid][-1]
    notice = kit.SESSIONS / f'{sid}.notices.jsonl'
    check('8. needs human past its deadline (4 s here, 2 h for real): the extension closed the tab, the record says '
          '"expired", the session has a notice', not still and last['event'] == 'expired' and notice.exists()
          and str(tid) not in kit.read_open(), (r.stdout[-120:], still, last['event'], round(time.time() - t0, 1)))


def main():
    profile = SCRATCH / 'profile'
    shutil.rmtree(profile, ignore_errors=True)
    (profile / 'NativeMessagingHosts').mkdir(parents=True)
    host_sh = SCRATCH / 'host.sh'               # what agent-chrome/install.sh's manifest points to, with the test's record
    host_sh.write_text(f"#!/bin/sh\nCHROME_KIT_TEST=1 CHROME_STATE='{STATE}' CHROME_TEST_PS='{PS}' CHROME_TEST_DESKTOPS='{DESKS}' exec /usr/bin/python3 '{code('native_host.py')}' \"$@\"\n")
    host_sh.chmod(0o755)
    (profile / 'NativeMessagingHosts' / f'{HOST}.json').write_text(json.dumps(
        {'name': HOST, 'description': 'test', 'path': str(host_sh), 'type': 'stdio', 'allowed_origins': [f'chrome-extension://{EXT_ID}/']}))
    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Pages)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{srv.server_port}'
    proc = subprocess.Popen([sys.argv[1], '--headless=new', f'--user-data-dir={profile}', '--remote-debugging-port=0',
                             '--no-first-run', '--no-default-browser-check', '--window-size=1280,800',
                             # 1 Nov 2026 19:20: without these, Chrome for Testing 152 headless never finished loading a
                             # page on this Mac (it had at 19:11); the launcher's branded Chrome was not affected
                             '--disable-renderer-backgrounding', '--disable-background-timer-throttling',
                             '--disable-backgrounding-occluded-windows',
                             f'--load-extension={EXT}', f'--disable-extensions-except={EXT}', 'about:blank'],
                            stdout=subprocess.DEVNULL, stderr=open(SCRATCH / 'chrome.stderr.log', 'w'))
    try:
        port_file = profile / 'DevToolsActivePort'
        for _ in range(120):
            if port_file.exists() and port_file.read_text().strip():
                break
            time.sleep(0.25)
        with sync_playwright() as p:
            ctx = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port_file.read_text().split()[0]}").contexts[0]
            ctl = ctx.new_page()
            ctl.goto(f'chrome-extension://{EXT_ID}/sidepanel.html')
            check('extension loaded with its fixed id', ctl.title() == 'Agent tab note', ctl.title())
            newest = lambda: max(t['id'] for t in ctl.evaluate('chrome.tabs.query({})'))
            badge = lambda t: ctl.evaluate(f'chrome.action.getBadgeText({{tabId: {t}}})')

            # 1. a session opens a tab and says the user must act: the bar shows the required fields, covers nothing
            page = ctx.new_page()
            page.set_viewport_size({'width': 1280, 'height': 720})
            page.goto(f'{base}/apply')
            tid = newest()
            page.screenshot(path=str(SHOTS / 'ext_bar_before.png'))
            kit.record([{'event': 'open', 'tab_id': tid, 'url': f'{base}/apply', 'profile': 'Claude - LinkedIn',
                         'device_id': GEN}], {'session_id': SID, 'cwd': str(PROJ)})
            claim('authorize-tab', 'Apply to job 4312 (Data Engineer, Zurich)', '--project', 'job-applications')
            active = lambda t: ctl.evaluate(f'chrome.tabs.get({t}).then(t => t.active)')
            other = ctx.new_page()            # the human is elsewhere: another tab in front
            other.goto(f'{base}/job')
            time.sleep(2)
            claim('mark-as-needing-human', 'solve the captcha')
            time.sleep(2)
            check('mark-as-needing-human: the tab is never brought to the front (the bar and badge say it)', not active(tid))
            other.close()
            time.sleep(1)
            txt = bar_text(page)
            opened = kit.read_open()[str(tid)]['opened_ts']
            day = time.strftime('%d', time.localtime(opened))
            check('bar on top, red, badge "!"', bar_on_top(page) and badge(tid) == '!')
            check('bar fields: opened (date + time), session UUID, project, purpose, NEEDS HUMAN with its deadline; no job',
                  all(s in txt for s in ['opened', day, SID, 'job-applications', 'Apply to job 4312',
                                         'NEEDS HUMAN: solve the captcha', 'if nobody acts'])
                  and 'job ' not in txt.replace('job-applications', '').replace('to job', ''), txt)
            covered = page.evaluate(MEASURE)
            check('nothing covered (page and its fixed header pushed down)', covered == [], covered)
            page.screenshot(path=str(SHOTS / 'ext_bar_after.png'))
            page.reload()
            time.sleep(1)
            check('after a reload: bar back, nothing covered', bar_on_top(page) and page.evaluate(MEASURE) == [])

            # 2. a tab opened by a scheduled job: the bar names the job
            jpage = ctx.new_page()
            jpage.set_viewport_size({'width': 1280, 'height': 720})
            jpage.goto(f'{base}/job')
            jtid = newest()
            kit.record([{'event': 'open', 'tab_id': jtid, 'url': f'{base}/job', 'profile': 'Claude - Account A', 'device_id': GEN,
                         'purpose': 'post the weekly listing', 'job': 'marketplace-seller.post'}], {'session_id': SID2, 'cwd': str(PROJ)})
            time.sleep(2)
            jtxt = bar_text(jpage)
            check('a job\'s tab: the bar shows the job', 'job' in jtxt and 'marketplace-seller.post' in jtxt, jtxt)
            jpage.screenshot(path=str(SHOTS / 'ext_bar_job.png'))
            jpage.close()

            # 3. comment round trip: typed in the side panel -> comments.jsonl; the agent's reply (agent-chrome reply-to-human)
            sp = ctx.new_page()
            sp.set_viewport_size({'width': 380, 'height': 640})
            sp.goto(f'chrome-extension://{EXT_ID}/sidepanel.html?tabId={tid}')
            time.sleep(1)
            body = sp.inner_text('body')
            form_shown = lambda: sp.evaluate('!document.getElementById("send").hidden && getComputedStyle(document.getElementById("send")).display !== "none"')
            check('side panel, mode single: "Answer in the terminal: session <id>", no comment box',
                  f'Answer in the terminal: session {SID}' in body and not form_shown(), body[:200])
            sp.screenshot(path=str(SHOTS / 'ext_side_panel_single.png'))
            # the same tab, now a subagent's (subagents mode: the human answers in the panel)
            claim('--agent-id', 'a1b2c3d4e5f6a7b8c', 'authorize-tab', 'Apply to job 4312 (Data Engineer, Zurich)', '--project', 'job-applications')
            kit.record([{'event': 'open', 'tab_id': tid, 'url': f'{base}/apply', 'profile': 'Claude - LinkedIn', 'device_id': GEN}],
                       {'session_id': SID, 'agent_id': 'a1b2c3d4e5f6a7b8c', 'mode': 'subagents', 'cwd': str(PROJ),
                        'purpose': 'Apply to job 4312 (Data Engineer, Zurich)'})
            claim('--agent-id', 'a1b2c3d4e5f6a7b8c', 'mark-as-needing-human', 'solve the captcha')
            time.sleep(2)
            body = sp.inner_text('body')
            check('side panel, a subagent\'s tab: the comment box, no terminal note', form_shown() and 'Answer in the terminal' not in body, body[:200])
            sp.fill('#text', 'Captcha solved, go on')
            sp.click('button')
            time.sleep(1.5)
            rows = [json.loads(x) for x in kit.COMMENTS.read_text().splitlines()] if kit.COMMENTS.exists() else []
            last = rows[-1] if rows else {}
            check('comment -> comments.jsonl: ts, dt, session_id, agent_id, tab_id, url, text',
                  list(last) == ['ts', 'dt', 'session_id', 'agent_id', 'tab_id', 'url', 'text'] and last['session_id'] == SID
                  and last['tab_id'] == tid and last['url'] == f'{base}/apply' and last['text'] == 'Captcha solved, go on', last)
            claim('--agent-id', 'a1b2c3d4e5f6a7b8c', 'mark-as-human-done')
            claim('--agent-id', 'a1b2c3d4e5f6a7b8c', 'reply-to-human', 'Thanks, I see it. Continuing the application.')
            time.sleep(2)
            body = sp.inner_text('body')
            check('side panel thread: the comment, then the agent\'s reply', body.find('Captcha solved') < body.find('Continuing the application') and 'Captcha solved' in body, body[:120])
            sp.screenshot(path=str(SHOTS / 'ext_side_panel_thread.png'))
            sp.close()
            txt = bar_text(page)
            check('bar after mark-as-human-done + reply-to-human: no NEEDS HUMAN, agent message shown, badge not "!"',
                  'NEEDS HUMAN' not in txt and 'agent: Thanks, I see it' in txt and badge(tid) != '!', txt)
            page.screenshot(path=str(SHOTS / 'ext_bar_reply.png'))

            # 4. side panel: no click -> refused; a click on the bar's "details · reply" -> opened
            sw = next(w for w in ctx.service_workers if EXT_ID in w.url)
            r = sw.evaluate(f'chrome.sidePanel.open({{tabId: {tid}}}).then(() => "opened", e => String(e))')
            check('side panel never opens by itself', r != 'opened', r)
            h = page.evaluate('parseFloat(getComputedStyle(document.documentElement).marginTop)')
            page.mouse.click(1280 - 120, h - 14)      # "details · reply": the bar's right end, on its last line
            time.sleep(1)
            r = ctl.evaluate("chrome.storage.session.get('lastOpen').then(r => r.lastOpen)")
            check('a click on the bar opens the side panel', r == 'opened', r)

            # 5. LinkedIn (a quiet site): no bar unless the user must act
            lpage = ctx.new_page()
            lpage.set_viewport_size({'width': 1280, 'height': 720})
            try:
                lpage.goto('https://www.linkedin.com/jobs/search?keywords=engineer&location=Zurich', wait_until='domcontentloaded', timeout=30000)
                lpage.wait_for_timeout(2000)
                ltid = newest()
                kit.record([{'event': 'open', 'tab_id': ltid, 'url': lpage.url, 'profile': 'Claude - LinkedIn', 'device_id': GEN,
                             'purpose': 'read job offers'}], {'session_id': SID2, 'cwd': str(PROJ)})
                time.sleep(2)
                check('LinkedIn, nothing to do: no bar, page untouched', not bar_on_top(lpage)
                      and lpage.evaluate('getComputedStyle(document.documentElement).marginTop') == '0px' and badge(ltid) == 'AI')
                kit.record([{'event': 'needs_human', 'tab_id': ltid, 'needs_human': 'log in to LinkedIn'}], {'session_id': SID2, 'cwd': str(PROJ)})
                time.sleep(2)
                covered = lpage.evaluate(MEASURE)
                check('LinkedIn, user must act: bar shown, nothing covered', bar_on_top(lpage) and covered == [], covered)
                lpage.screenshot(path=str(SHOTS / 'ext_bar_linkedin.png'))
            except Exception as e:  # noqa: BLE001  offline: skip, say so
                print(f'SKIP  LinkedIn checks: {str(e)[:80]}')
            lpage.close()

            # 6. the tab is closed in the record: bar and page margin gone
            kit.record([{'event': 'close', 'tab_id': tid}], {'session_id': SID, 'cwd': str(PROJ)})
            time.sleep(2)
            check('close: bar gone, page margin back to 0', not page.evaluate("!!document.querySelector('agent-tab-note')")
                  and page.evaluate('getComputedStyle(document.documentElement).marginTop') == '0px' and badge(tid) == '')

            expiry(ctx, ctl, base)
            windows(ctx, ctl, base)
    finally:
        proc.terminate()
        proc.wait(30)
        srv.shutdown()
    time.sleep(2)
    check('Chrome gone: its windows report removed (the host deletes it when the port closes)',
          not (STATE / 'windows' / 'Claude - Account A.json').exists())
    print(f'{sum(results)}/{len(results)} checks passed')
    sys.exit(0 if all(results) else 1)


if __name__ == '__main__':
    main()
