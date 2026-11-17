(function () {
  const $ = s => document.querySelector(s);
  const mk = (tag, cls, txt) => { const e = document.createElement(tag); if (cls) e.className = cls; if (txt != null) e.textContent = txt; return e; };
  const KEY = 'prtour-ide';
  let pref = {}; try { pref = JSON.parse(localStorage.getItem(KEY) || '{}'); } catch {}
  const save = () => { try { localStorage.setItem(KEY, JSON.stringify(pref)); } catch {} };
  const NARROW = matchMedia('(max-width: 1100px)');
  document.body.classList.add('ide');

  /* naslovna traka */
  const title = mk('header', 'ide-title');
  const P = typeof PRINFO !== 'undefined' ? PRINFO : {};
  const M = typeof META !== 'undefined' ? META : {};
  title.innerHTML = `<span class="logo">PR</span>
    <span class="crumb"><a class="mono hide-s" data-k="repo"></a><span class="sep hide-s">›</span><a class="pr" data-k="pr"></a>
    <a class="br" data-k="src"></a><span class="sep">→</span><a class="mono" data-k="dest"></a><span class="sep hide-s">·</span><span class="hide-s" data-k="author"></span>
    <span class="sep hide-s">·</span><a class="mono hide-s tour-ver" data-k="ver"></a></span>
    <span class="sp"></span>`;
  const host = M.host === 'bitbucket' ? 'Bitbucket' : M.host === 'azure' ? 'Azure DevOps' : 'GitHub';
  const branchUrl = b => b && M.repoUrl ? `${M.repoUrl}/${M.host === 'bitbucket' ? 'branch' : 'tree'}/${b.split('/').map(encodeURIComponent).join('/')}` : '';
  const commitUrl = sha => sha && M.repoUrl ? `${M.repoUrl}/${M.host === 'bitbucket' ? 'commits' : 'commit'}/${sha}` : '';
  const link = (k, text, href, tip) => {
    const a = title.querySelector(`[data-k="${k}"]`);
    a.textContent = text;
    if (href && a.tagName === 'A') { a.href = href; a.target = '_blank'; a.rel = 'noopener'; a.title = tip; }
  };
  link('repo', M.repo || '', M.repoUrl, `Repo na ${host}u`);
  link('pr', M.number ? `PR #${M.number}` : 'grana, bez PR-a', M.prUrl, M.number ? `PR na ${host}u` : `Usporedba s baznom granom na ${host}u`);
  link('src', P.source || '', branchUrl(P.source), `Grana na ${host}u`);
  link('dest', P.dest || '', branchUrl(P.dest), `Grana na ${host}u`);
  link('author', P.author || '');
  const ver = title.querySelector('.tour-ver'), at = (P.at || '').match(/^(\d{4})-(\d\d)-(\d\d)(?:[ T](\d\d:\d\d))?/);
  if (commitUrl(M.head)) { ver.href = commitUrl(M.head); ver.target = '_blank'; ver.rel = 'noopener'; }
  ver.textContent = [(M.head || '').slice(0, 7), at && `tour od ${+at[3]}.${+at[2]}.${at[4] ? ` u ${at[4]}` : ''}`].filter(Boolean).join(' · ');
  ver.title = `Tour je napravljen za commit ${(M.head || '?').slice(0, 7)}${P.at ? `; stanje PR-a s ${M.host === 'bitbucket' ? 'Bitbucketa' : 'GitHuba'} od ${P.at}` : ''}.`;
  const tgTree = mk('button', 'ide-tg'); tgTree.innerHTML = '<span>☰</span><span class="lbl">Fajlovi</span><kbd>Ctrl+B</kbd>';
  const tgCode = mk('button', 'ide-tg'); tgCode.innerHTML = '<span>&lt;/&gt;</span><span class="lbl">Kod</span><kbd>Ctrl+J</kbd>';
  title.querySelector('.logo').after(tgTree); title.append(tgCode);
  document.body.prepend(title);

  /* statusna traka */
  const st = mk('footer', 'ide-status');
  const ciFail = (P.ci || []).some(c => c.state === 'FAILED');
  const waiting = (P.approvals || []).filter(a => !a.approved).length;
  const plural = (n, one, few, many) => { const t = n % 100, u = n % 10; return t >= 11 && t <= 14 ? many : u === 1 ? one : u >= 2 && u <= 4 ? few : many; };
  const fresh = P.previousReview?.newCommits || 0;
  const pending = [waiting && `čeka ${waiting} ${plural(waiting, 'odobrenje', 'odobrenja', 'odobrenja')}`,
                   fresh && `${fresh} ${plural(fresh, 'novi commit', 'nova commita', 'novih commita')} od tvog reviewa`].filter(Boolean);
  // Red only for a real problem; waiting for review is the normal state of an open PR.
  const verdict = ciFail ? mk('button', 'verdict bad', `✕ CI pao${pending.length ? ' · ' + pending.join(' · ') : ''}`)
    : pending.length ? mk('button', 'verdict wait', `◷ ${pending.join(' · ')}`)
    : mk('button', 'verdict good', '✓ Može se mergati');
  verdict.title = 'Na Dashboard, na zaglavlje PR-a';
  verdict.addEventListener('click', () => typeof edShowPage === 'function' ? edShowPage('dashboard') : window.scrollTo({ top: 0, behavior: 'smooth' }));
  const br = mk(branchUrl(P.source) ? 'a' : 'span', 'mono hide-s', `⎇ ${P.source || ''} → ${P.dest || ''}`);
  if (br.tagName === 'A') { br.href = branchUrl(P.source); br.target = '_blank'; br.rel = 'noopener'; br.title = `Grana na ${host}u`; }
  const size = mk('span', 'mono hide-s'); size.innerHTML = `${P.files ?? ''} fajlova <span class="a">+${P.added ?? ''}</span> <span class="d">−${P.removed ?? ''}</span>`;
  const cur = mk('span', 'mono hide-s');
  const codeSt = mk('button', 'mono');
  st.append(verdict, br, size, mk('span', 'sp'), cur, codeSt);
  document.body.append(st);

  /* explorer */
  const ex = mk('aside', 'ide-explorer'); ex.setAttribute('aria-label', 'Fajlovi PR-a');
  const isTest = p => /(^|\/)[^/]*\.Tests?(\.[^/]*)?(\/|$)/i.test(p) || /Tests?\.cs$/i.test(p);
  const isNoise = p => /\.(csproj|sln|resx|config|png|ico|svg|editorconfig|props|targets|keep|gitkeep|toml|bat|ps1|sh)$/i.test(p) || /(\.Designer\.cs|AssemblyInfo\.cs)$/i.test(p);
  const KEYF = new Set([...Object.values(typeof CODE !== 'undefined' ? CODE : {}).map(c => c.file), ...Object.keys(typeof OUTLINE !== 'undefined' ? OUTLINE : {})]);
  const files = Object.entries((typeof SRC !== 'undefined' && SRC.files) || {}).filter(([, f]) => f.added != null || f.removed != null)
    .map(([p, f]) => ({ p, s: (f.status || 'M')[0], add: f.added, del: f.removed, t: isTest(p), n: isNoise(p), k: KEYF.has(p), name: p.split('/').pop(), tests: [] }));
  files.filter(f => f.t).forEach(t => {
    const subj = t.name.replace(/Tests?\.cs$/i, '.cs');
    const s = files.find(f => !f.t && f.name === subj);
    if (s) { s.tests.push(t); t.of = s; }
  });
  const tops = [...new Set(files.map(f => f.p.split('/')[0]))];
  let prefix = '';
  {
    const cands = {};
    tops.forEach(t => { const tk = t.split('.'); for (let i = 1; i < tk.length; i++) { const p = tk.slice(0, i).join('.'); cands[p] = (cands[p] || 0) + 1; } });
    const best = Object.entries(cands).filter(([, n]) => n >= 2).sort((a, b) => b[1] * b[0].length - a[1] * a[0].length)[0];
    if (best) prefix = best[0];
  }
  const treeParts = p => { const parts = p.split('/'); return prefix && parts[0].startsWith(prefix + '.') ? [prefix, parts[0].slice(prefix.length + 1), ...parts.slice(1)] : parts; };
  const LENS = { bitno: 'Bitno', bez: 'Bez testova', testovi: 'Samo testovi', sve: 'Sve' };
  if (!files.some(f => f.k)) LENS.bitno = null;
  let lens = pref.lens && LENS[pref.lens] ? pref.lens : (LENS.bitno ? 'bitno' : 'bez');
  const visible = f => lens === 'sve' || (lens === 'testovi' ? !!f.t : lens === 'bez' ? !f.t && !f.n : f.k && !f.t);
  ex.innerHTML = `<div class="ex-h">Fajlovi PR-a <span class="c"></span><button type="button" title="Sažmi sve">⊟</button></div>
    <div class="ex-search"><input type="search" placeholder="Traži fajl…" aria-label="Traži fajl"></div>
    <div class="ex-filters" role="toolbar" aria-label="Filteri"></div>
    <div class="ex-tree" role="tree"></div><div class="ex-resizer" title="Povuci za širinu · dvoklik vraća zadanu"></div>`;
  const cntEl = ex.querySelector('.ex-h .c');
  const LENS_HINT = { bitno: 'fajlovi koje tour objašnjava', bez: 'bez testova i projektnih fajlova', testovi: 'samo testovi koje PR dira', sve: 'svi fajlovi PR-a' };
  title.after(ex);
  const treeEl = ex.querySelector('.ex-tree'), q = ex.querySelector('.ex-search input');

  const root = { dirs: {}, files: [] };
  files.forEach(f => {
    const parts = treeParts(f.p); let n = root;
    parts.slice(0, -1).forEach(d => { n = n.dirs[d] ||= { dirs: {}, files: [] }; });
    n.files.push(f);
  });
  const icon = n => { const e = n.split('.').pop().toLowerCase();
    return e === 'cs' ? ['cs', 'C#'] : (e === 'xaml' || e === 'xml' || e === 'odx') ? ['xml', '<>'] : e === 'json' ? ['json', '{}'] : e.endsWith('proj') ? ['proj', 'PJ'] : ['', '··']; };
  const closed = new Set(pref.closed || []);
  let activePath = null;

  /* Pregled fajlova živi u touru (rvFileState, rvRingSvg, rvHidden); stablo ih samo prikazuje kad postoje. */
  const rvState = p => typeof window.rvFileState === 'function' ? window.rvFileState(p) : null;
  const allUnder = n => [...n.files, ...Object.values(n.dirs).flatMap(allUnder)];
  /* Svi filteri u jednom redu ispod pretrage: leća (padajući izbornik) i tri prekidača koji svijetle kad su uključeni.
     Tvoji komentari i AI razgovori (iz toura) imaju i oznaku uz fajl. */
  const markOn = pref.marks || (pref.marks = {});
  const UNSEEN_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4"><circle cx="12" cy="12" r="7.5"/></svg>';
  const COMMENT_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M4.5 5.5h15v10h-9l-4.5 3.5v-3.5h-1.5z"/></svg>';
  const filtersEl = ex.querySelector('.ex-filters');
  const hasRv = () => typeof window.rvHidden === 'function';
  const setLens = k => { lens = k; pref.lens = k; save(); render(); };
  const toggleMark = k => { markOn[k] = !markOn[k]; save(); render(); };
  const toggleHide = () => { if (typeof window.rvToggleHide === 'function') window.rvToggleHide(); else render(); };
  function renderFilters(nC, nAi, nNew, nD, nF) {
    const hide = hasRv() && window.rvHidden();
    filtersEl.innerHTML = '';
    const sel = mk('select', 'ef-lens' + (lens !== 'sve' ? ' on' : ''));
    sel.title = 'Koje fajlove prikazati';
    Object.entries(LENS).forEach(([k, label]) => {
      if (!label) return;
      const o = mk('option', '', label); o.value = k; o.title = LENS_HINT[k]; o.selected = lens === k;
      sel.append(o);
    });
    sel.addEventListener('change', () => setLens(sel.value));
    filtersEl.append(sel);
    const tog = (on, svg, label, n, title, onClick) => {
      const b = mk('button', 'ef-tog' + (on ? ' on' : '')); b.type = 'button';
      b.setAttribute('aria-pressed', on); b.title = title;
      b.innerHTML = svg + (n != null ? `<b>${n}</b>` : '') + (label ? `<span class="lbl">${label}</span>` : '');
      b.disabled = n === 0 && !on;
      b.addEventListener('click', onClick);
      filtersEl.append(b);
    };
    if (hasRv()) tog(hide, UNSEEN_SVG, 'nepregledano', nNew, hide ? 'Makni filter: prikaži i pregledane (H)' : 'Samo nepregledani fajlovi (H)', toggleHide);
    tog(!!markOn.c, COMMENT_SVG, 'komentari', nC, markOn.c ? 'Makni filter: fajlovi s mojim komentarima' : 'Samo fajlovi s mojim komentarima', () => toggleMark('c'));
    tog(!!markOn.ai, '<i>✦</i>', 'AI', nAi, markOn.ai ? 'Makni filter: fajlovi s AI razgovorom' : 'Samo fajlovi s AI razgovorom', () => toggleMark('ai'));
    if (nF || markOn.f) tog(!!markOn.f, '<i>!</i>', 'nalazi', nF, markOn.f ? 'Makni filter: fajlovi s nalazima reviewa' : 'Samo fajlovi s otvorenim nalazima reviewa', () => toggleMark('f'));
    if (nD || markOn.d) tog(!!markOn.d, '<i>🗨</i>', 'rasprava', nD, markOn.d ? 'Makni filter: fajlovi s raspravom na PR-u' : 'Samo fajlovi o kojima se raspravlja na PR-u', () => toggleMark('d'));
  }
  function render() {
    const term = q.value.trim().toLowerCase();
    const marks = typeof window.treeMarksAll === 'function' ? window.treeMarksAll() : {};
    const markF = !!(markOn.c || markOn.ai || markOn.d || markOn.f);
    const marked = f => { const m = marks[f.p]; return !!m && ((markOn.c && m.c > 0) || (markOn.ai && m.ai > 0) || (markOn.d && m.d > 0) || (markOn.f && m.f > 0)); };
    const hideViewed = hasRv() && window.rvHidden();
    treeEl.innerHTML = '';
    const ul = mk('ul'); ul.setAttribute('role', 'group');
    let shown = 0;
    const walk = (node, path, depth, list) => {
      let total = 0;
      Object.keys(node.dirs).sort().forEach(name => {
        let d = node.dirs[name], label = name, full = path ? path + '/' + name : name;
        while (Object.keys(d.dirs).length === 1 && !d.files.length && depth > 0 && !(depth === 1 && path === prefix)) { const k = Object.keys(d.dirs)[0]; label += '/' + k; full += '/' + k; d = d.dirs[k]; }
        const under = allUnder(d), seenN = under.filter(f => rvState(f.p)?.viewed).length, full_ = rvState(under[0]?.p) && seenN === under.length;
        const hasActive = !term && under.some(f => f.p === activePath);
        if (hideViewed && full_ && !term && !hasActive) return;
        if (markF && !under.some(marked) && !hasActive) return;
        const sub = mk('ul');
        const cnt = walk(d, full, depth + 1, sub);
        total += cnt;
        if (!cnt) return;
        const open = term || !closed.has(full);
        const li = mk('li');
        const b = mk('button', 'ex-row dir' + ((depth === 0 && name !== prefix) || (depth === 1 && path === prefix) ? ' proj' : depth === 0 ? ' grp' : '') + (full_ ? ' rv-full' : ''));
        b.style.paddingLeft = (8 + depth * 12) + 'px';
        const isGroup = depth === 0 && name === prefix;
        const dc = rvState(under[0]?.p) ? `${seenN}/${under.length}` : cnt;
        b.innerHTML = `<span class="chev">${open ? '▾' : '▸'}</span><span class="ic dir">${full_ ? '✓' : isGroup ? '◫' : (depth === 0 || (depth === 1 && path === prefix)) ? '▣' : '▭'}</span><span class="nm"></span><span class="dc">${dc}</span>`;
        b.querySelector('.nm').textContent = label; b.title = full;
        b.addEventListener('click', () => { closed.has(full) ? closed.delete(full) : closed.add(full); pref.closed = [...closed]; save(); render(); });
        li.append(b); if (open) li.append(sub); list.append(li);
      });
      let c = 0;
      node.files.slice().sort((a, b) => a.name.localeCompare(b.name)).forEach(f => {
        const outside = !visible(f) || (markF && !marked(f));
        const pinned = !term && f.p === activePath;
        if (term ? !f.p.toLowerCase().includes(term) : outside && !pinned) return;
        if (term && markF && !marked(f)) return;
        const rv = rvState(f.p);
        if (hideViewed && rv?.viewed && f.p !== activePath && !term) return;
        c++; shown++;
        const [cls, glyph] = icon(f.name);
        const li = mk('li');
        const b = mk('button', 'ex-row file ' + f.s + (f.p === activePath ? ' on' : '') + (rv?.viewed ? ' rv-done' : '') + (pinned && outside ? ' outside' : ''));
        b.style.paddingLeft = (8 + depth * 12) + 'px';
        const m = marks[f.p];
        b.innerHTML = `<span class="chev"></span>${rv ? window.rvRingSvg(f.p) : ''}<span class="ic ${cls}">${glyph}</span><span class="nm"></span>${m?.c ? `<span class="tm c" title="Tvoji komentari: ${m.c} (klik otvara prvi)">${COMMENT_SVG}${m.c}</span>` : ''}${m?.ai ? `<span class="tm ai" title="AI razgovori: ${m.ai} (klik otvara zadnji)">✦${m.ai}</span>` : ''}${m?.f ? `<span class="tm f ${m.fSev || 'low'}" title="Nalazi reviewa: ${m.f} otvorenih (klik otvara prvi)">!${m.f}</span>` : ''}${m?.d ? `<span class="tm d${m.dOpen ? ' open' : ''}" title="Rasprava na PR-u: ${m.d} niti${m.dOpen ? `, ${m.dOpen} otvorenih` : ', sve riješene'} (klik otvara)">🗨${m.d}</span>` : ''}${m?.n ? `<span class="tm n" title="Promijenjen od kad je tour napravljen (klik otvara prvu novu liniju)">Δ</span>` : ''}${f.tests.length && lens !== 'sve' ? `<span class="tb" title="Testovi: ${f.tests.map(t => t.name).join(', ')}">T${f.tests.length}</span>` : ''}<span class="st ${f.s}">${f.s}</span>`;
        b.querySelector('.nm').textContent = f.name;
        b.title = f.p + { A: ' · novi', D: ' · obrisan', M: ' · izmijenjen', R: ' · preimenovan' }[f.s] + ` · +${f.add ?? 0} −${f.del ?? 0}` + (pinned && outside ? ' · otvoren, ali izvan trenutnog filtera' : '');
        b.addEventListener('click', e => {
          const tm = e.target.closest('.tm');
          if (tm && typeof window.treeMarkOpen === 'function') { showCode(true); window.treeMarkOpen(f.p, ['c', 'ai', 'd', 'n', 'f'].find(k => tm.classList.contains(k))); return; }
          if (e.target.closest('.tb')) { openFile(f.tests[0]); return; }
          openFile(f);
        });
        li.append(b); list.append(li);
      });
      return total + c;
    };
    walk(root, '', 0, ul);
    treeEl.append(shown ? ul : mk('div', 'ex-empty', term ? 'Nema fajla s tim imenom.' : 'Nijedan fajl ne prolazi ove filtere.'));
    const nC = files.filter(f => marks[f.p]?.c > 0).length, nAi = files.filter(f => marks[f.p]?.ai > 0).length;
    renderFilters(nC, nAi, files.filter(f => rvState(f.p) && !rvState(f.p).viewed).length, files.filter(f => marks[f.p]?.d > 0).length, files.filter(f => marks[f.p]?.f > 0).length);
    cntEl.textContent = term || (lens === 'sve' && !markF) ? files.length : `${shown} / ${files.length}`;
    if (!term && lens !== 'sve' && !markF) {
      const hid = files.filter(f => !visible(f));
      const t = hid.filter(f => f.t).length, n = hid.filter(f => f.n && !f.t).length, o = hid.length - t - n;
      if (hid.length) {
        const b = mk('button', 'ex-hidden');
        b.innerHTML = `<span>Skriveno ${hid.length}</span><small>${[t && t + ' testova', n && n + ' projektnih', o && o + ' ostalih'].filter(Boolean).join(' · ')}</small>`;
        b.title = 'Prikaži sve fajlove';
        b.addEventListener('click', () => { lens = 'sve'; pref.lens = 'sve'; save(); render(); });
        treeEl.append(b);
      }
    }
  }
  q.addEventListener('input', render);
  window.ideRenderTree = render;
  const treeOrder = [];
  (function rec(n) { Object.keys(n.dirs).sort().forEach(k => rec(n.dirs[k])); n.files.slice().sort((a, b) => a.name.localeCompare(b.name)).forEach(f => treeOrder.push(f.p)); })(root);
  window.ideOrder = () => treeOrder;
  // "Sljedeći nepregledan" in the tour walks only the files this filter shows
  window.ideInFilter = p => {
    const f = files.find(x => x.p === p);
    if (!f) return true;
    const m = typeof window.treeMarksAll === 'function' ? window.treeMarksAll()[p] : null;
    const markF = !!(markOn.c || markOn.ai || markOn.d || markOn.f);
    return visible(f) && (!markF || (!!m && ((markOn.c && m.c > 0) || (markOn.ai && m.ai > 0) || (markOn.d && m.d > 0) || (markOn.f && m.f > 0))));
  };
  window.ideTreePath = p => treeParts(p).join('/');
  ex.querySelector('.ex-h button').addEventListener('click', () => {
    const all = []; const rec = (n, p, d) => Object.keys(n.dirs).forEach(k => { const f = p ? p + '/' + k : k; if (d === 0) all.push(f); rec(n.dirs[k], f, d + 1); });
    rec(root, '', 0); all.forEach(f => closed.add(f)); pref.closed = [...closed]; save(); render();
  });

  function openFile(f) {
    showCode(true);
    if (typeof openCommentTarget === 'function') openCommentTarget({ file: f.p, side: f.s === 'D' ? 'base' : 'head' });
    if (NARROW.matches) setTree(false);
  }

  /* prekidači */
  function setTree(on) {
    document.body.classList.toggle('ide-tree-off', !on);
    tgTree.setAttribute('aria-pressed', on);
    if (!NARROW.matches) { pref.tree = on; save(); }
  }
  function codeIsOn() {
    return WIDE.matches ? !document.body.classList.contains('ide-code-off') : drawer.classList.contains('open');
  }
  function showCode(on) {
    if (WIDE.matches) { document.body.classList.toggle('ide-code-off', !on); pref.code = on; save(); }
    else drawer.classList.toggle('open', on);
    syncCode();
  }
  function syncCode() {
    const on = codeIsOn();
    tgCode.setAttribute('aria-pressed', on);
    codeSt.textContent = on ? '</> kod: otvoren' : '</> kod: zatvoren';
  }
  tgTree.addEventListener('click', () => setTree(document.body.classList.contains('ide-tree-off')));
  tgCode.addEventListener('click', () => showCode(!codeIsOn()));
  codeSt.addEventListener('click', () => showCode(!codeIsOn()));
  document.addEventListener('keydown', e => {
    if (!(e.ctrlKey || e.metaKey) || e.altKey) return;
    const k = e.key.toLowerCase();
    if (k === 'b') { e.preventDefault(); setTree(document.body.classList.contains('ide-tree-off')); }
    if (k === 'j') { e.preventDefault(); showCode(!codeIsOn()); }
  });
  new MutationObserver(syncCode).observe(drawer, { attributes: true, attributeFilter: ['class'] });
  const applyWidth = () => { setTree(NARROW.matches ? false : pref.tree !== false); if (WIDE.matches) document.body.classList.toggle('ide-code-off', pref.code === false); syncCode(); };
  NARROW.addEventListener('change', applyWidth); WIDE.addEventListener('change', applyWidth);

  /* kod se otvara kad korisnik klikne oznaku: uključi panel i označi fajl u stablu */
  const origRender = window.renderView;
  if (typeof origRender === 'function') {
    window.renderView = function () {
      const r = origRender.apply(this, arguments);
      if (!codeIsOn()) showCode(true);
      try {
        const p = view?.type === 'file' ? view.path : CODE[view?.key]?.file;
        if (p && p !== activePath) {
          activePath = p;
          p.split('/').slice(0, -1).reduce((acc, d) => { const f = acc ? acc + '/' + d : d; closed.delete(f); return f; }, '');
          render();
          const r2 = treeEl.querySelector('.ex-row.on'); if (r2) treeEl.scrollTop = r2.offsetTop - treeEl.clientHeight / 3;
          cur.textContent = p.split('/').pop();
        }
      } catch {}
      return r;
    };
  }

  /* širina stabla */
  const rz = ex.querySelector('.ex-resizer');
  const setTreeW = w => { if (w == null) document.documentElement.style.removeProperty('--tree-w'); else document.documentElement.style.setProperty('--tree-w', Math.round(Math.max(200, Math.min(w, 560))) + 'px'); };
  if (pref.treeW) setTreeW(pref.treeW);
  rz.addEventListener('pointerdown', e => {
    e.preventDefault(); rz.setPointerCapture(e.pointerId); document.body.classList.add('resizing');
    const move = ev => setTreeW(ev.clientX);
    const up = ev => { rz.removeEventListener('pointermove', move); rz.removeEventListener('pointerup', up); document.body.classList.remove('resizing');
      pref.treeW = parseInt(getComputedStyle(document.documentElement).getPropertyValue('--tree-w')) || null; save(); };
    rz.addEventListener('pointermove', move); rz.addEventListener('pointerup', up);
  });
  rz.addEventListener('dblclick', () => { setTreeW(null); pref.treeW = null; save(); });

  render();
  applyWidth();
})();
