const $ = id => document.getElementById(id);
const stages = [
  ['waiting', 'Waiting', '#667185'], ['ready', 'Ready', '#316f9f'],
  ['implementing', 'Implementing', '#6553cd'], ['reviewing', 'Reviewing', '#93631c'],
  ['done', 'Done', '#14745d'], ['blocked', 'Blocked', '#ae3f50'],
];
let snapshot = null, selectedIssue = null, busy = false, revision = 0;
const node = (tag, className, text) => {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
};
function duration(seconds) {
  if (seconds == null) return 'unknown';
  const minutes = Math.floor(Math.max(0, seconds) / 60);
  return minutes >= 60 ? `${Math.floor(minutes / 60)}h ${minutes % 60}m` : minutes ? `${minutes}m` : '<1m';
}
function phase(row) {
  return ({implement: 'Implementing', review: `${row.axis || ''} review`, fix: 'Fixing review findings'})[row.role] || row.role || 'Attempt';
}
function agentIcon(provider, current = false) {
  const name = {claude: 'Claude', codex: 'Codex'}[provider];
  if (!name) return node('span', 'unknown-agent', '?');
  const icon = node('img', `agent-icon${current ? ' current' : ''}`);
  icon.src = `/static/icons/${provider}.svg${provider === 'codex' ? '?v=openai-green' : ''}`;
  icon.alt = name;
  icon.title = current ? `${name} · current agent` : name;
  return icon;
}
function agents(attempts, current = false) {
  const group = node('div', 'agents');
  group.append(...[...new Set(attempts.map(row => row.provider).filter(Boolean))].map(provider => agentIcon(provider, current)));
  return group;
}
async function get(url, timeout = 12000) {
  const response = await fetch(url, {cache: 'no-store', signal: AbortSignal.timeout(timeout)});
  if (!response.ok) throw new Error(`Cannot read status (${response.status}). Retrying automatically.`);
  return response.json();
}
function options(select, values, preferred) {
  const selection = values.includes(preferred) ? preferred : values[0];
  if (JSON.stringify([...select.options].map(option => option.value)) !== JSON.stringify(values)) {
    select.replaceChildren(...values.map(value => new Option(value, value)));
  }
  select.value = selection || '';
}
function render(board) {
  snapshot = board;
  const done = board.issues.filter(issue => issue.stage === 'done').length;
  $('completion').textContent = `${done} of ${board.issues.length} issues done`;
  $('progress').max = board.issues.length || 1;
  $('progress').value = done;
  $('counts').textContent = `${board.issues.filter(issue => issue.stage === 'ready').length} ready · ${board.issues.filter(issue => issue.stage === 'blocked').length} blocked`;
  $('issue-count').textContent = board.issues.length;
  $('pulse').classList.toggle('active', board.runner.active);
  const active = board.runner.attempts.filter(row => row.active);
  $('worker-state').textContent = board.runner.active ? (active.length ? 'Worker running' : 'Runner active · between attempts or on another cycle') : 'Runner stopped';
  $('activity').replaceChildren(...active.map(row => {
    const element = node('div', 'attempt');
    const issue = board.issues.find(issue => issue.active_attempts.some(attempt => attempt.attempt === row.attempt));
    const heading = node('strong', 'attempt-heading');
    heading.append(agentIcon(row.provider, true), node('b', '', `Issue ${issue?.number || '?'} · ${phase(row)}`));
    element.append(heading, node('span', '', `${duration(row.elapsed_seconds)} elapsed · log output ${row.log_age_seconds == null ? 'unknown' : duration(row.log_age_seconds) + ' ago'}`));
    return element;
  }));
  if (!active.length) $('activity').append(node('span', '', board.runner.active ? 'Checking worker artifacts every 4 seconds.' : 'Issue status is preserved. No worker currently holds the runner lock.'));
  $('cooldowns').replaceChildren(...Object.entries(board.runner.cooldowns).map(([provider, reset]) => {
    const element = node('div', 'cooldown');
    element.append(agentIcon(provider), node('span', '', `Quota reset in ${duration(reset - Date.now() / 1000)} · ${new Date(reset * 1000).toLocaleTimeString()}`));
    return element;
  }));
  const focused = document.activeElement?.dataset?.issue;
  $('board').replaceChildren(...stages.map(([key, label, color]) => {
    const issues = board.issues.filter(issue => issue.stage === key);
    const column = node('section', 'column');
    column.style.setProperty('--stage', color);
    const heading = node('h3', '', label);
    if (['implementing', 'reviewing'].includes(key)) heading.append(agents(issues.flatMap(issue => issue.active_attempts), true));
    heading.append(node('span', 'column-count', issues.length));
    column.append(heading, ...issues.map(card));
    if (!issues.length) column.append(node('p', 'empty', 'No issues'));
    return column;
  }));
  if (focused) [...document.querySelectorAll('.card')].find(element => element.dataset.issue === focused)?.focus({preventScroll: true});
  if ($('details').open) updateDetails();
}
function card(issue) {
  const button = node('button', `card${issue.active_attempts.length ? ' active' : ''}`);
  button.dataset.issue = issue.number;
  const header = node('div', 'card-header');
  header.append(node('div', 'card-number', `ISSUE ${issue.number}`), agents(issue.active_attempts.length ? issue.active_attempts : issue.attempts, !!issue.active_attempts.length));
  button.append(header, node('div', 'card-title', issue.title.replace(/^(Issue\s+)?\d+\s*[:—–.\-]\s*/i, '')));
  if (issue.active_attempts.length) {
    const badge = node('div', 'badge');
    badge.append(agents(issue.active_attempts, true), node('span', '', issue.active_attempts.map(phase).join(' + ')));
    button.append(badge);
  }
  if (issue.progress) button.append(node('div', 'card-progress', issue.progress));
  const meta = node('div', 'card-meta');
  meta.append(node('span', '', `${issue.attempts.length} attempts`), node('span', '', issue.attempts.length ? `${duration(issue.total_attempt_seconds)} recorded` : 'Not started'));
  button.append(meta);
  const reviews = (issue.reviews || []).filter(report => report.status === 'available');
  if (reviews.length) button.append(node('div', 'review-count', `${reviews.length} reviewer report${reviews.length === 1 ? '' : 's'}`));
  if (issue.stage === 'waiting') button.append(node('div', 'card-blockers', `Waiting for ${issue.blockers.map(number => '#' + number).join(', ') || 'dependencies'}`));
  if (!snapshot.runner.active && ['implementing', 'reviewing'].includes(issue.stage)) button.append(node('div', 'card-blockers', 'Worker stopped · unfinished'));
  button.addEventListener('click', () => {
    selectedIssue = issue.number;
    updateDetails();
    $('details').showModal();
    $('details').querySelector('.dialog-body').scrollTop = 0;
    $('detail-title').focus({preventScroll: true});
  });
  return button;
}
function updateDetails() {
  const issue = snapshot?.issues.find(issue => issue.number === selectedIssue);
  if (!issue) { $('details').close(); return; }
  $('detail-title').textContent = issue.title;
  $('detail-stage').textContent = `ISSUE ${issue.number} / ${issue.stage.toUpperCase()}`;
  $('detail-content').textContent = issue.content;
  $('detail-attempts').replaceChildren(...issue.attempts.map(row => {
    const element = node('div', 'history-row');
    element.append(agentIcon(row.provider, row.active), node('span', '', `${phase(row)} · ${row.model || 'CLI default'} · ${duration(row.elapsed_seconds)} · ${row.outcome || (row.active ? 'running' : 'unfinished; duration unknown')}`));
    return element;
  }));
  const reports = issue.reviews || [];
  const signature = JSON.stringify(reports);
  if ($('detail-reviews').dataset.signature !== signature) {
    $('detail-reviews').dataset.signature = signature;
    $('detail-reviews').replaceChildren(...reports.map(report => {
      const element = node('section', 'review-report');
      const heading = node('h4', 'review-heading');
      if (report.provider) heading.append(agentIcon(report.provider));
      heading.append(node('span', '', `${report.axis === 'spec' ? 'Spec' : 'Standards'} review`));
      element.append(heading, report.status === 'available' ? node('pre', '', report.content) : node('p', 'quota-note', report.status === 'missing' ? 'No saved report yet.' : 'Report unavailable; retrying next refresh.'));
      return element;
    }));
  }
}
async function refreshQuotas() {
  try {
    const quotas = await get('/api/quotas', 35000);
    const panels = [];
    for (const provider of ['claude', 'codex']) {
      const accounts = quotas.accounts.filter(account => account.provider === provider);
      for (const account of accounts.length ? accounts : [{windows: [], captured_at: null}]) {
        const panel = node('div', 'quota-panel');
        const heading = node('div', 'quota-heading');
        heading.append(agentIcon(provider), node('strong', '', 'Account quota'));
        const age = account.captured_at ? (Date.now() - Date.parse(account.captured_at)) / 1000 : null;
        const captured = node('span', 'quota-captured', age == null ? 'Unavailable' : `Last reading · ${duration(age)} ago`);
        const stale = account.stale || age > 180;
        captured.classList.toggle('stale', !!stale);
        captured.title = 'Time Moshi last obtained this quota reading. The dashboard checks for a newer reading every minute.';
        heading.append(captured);
        panel.append(heading);
        for (const window of account.windows) {
          const row = node('div', 'quota-window');
          const label = node('div', 'quota-label');
          label.append(node('span', '', window.label), node('strong', '', `${window.used_percent}% used`));
          const bar = node('progress');
          bar.max = 100; bar.value = window.used_percent;
          bar.setAttribute('aria-label', `${provider} ${window.label} quota used`);
          const reset = Date.parse(window.resets_at);
          row.append(label, bar, node('span', 'quota-reset', Number.isFinite(reset) ? `${reset > Date.now() ? 'Resets in ' + duration((reset - Date.now()) / 1000) : 'Reset time passed · awaiting new snapshot'} · ${new Date(reset).toLocaleString()}` : 'Reset time unavailable'));
          panel.append(row);
        }
        if (!account.windows.length) panel.append(node('p', 'quota-note', 'No quota snapshot available.'));
        else if (stale) panel.append(node('p', 'quota-note', 'Moshi has no newer reading available. These percentages may have changed.'));
        panels.push(panel);
      }
    }
    panels.push(node('p', 'quota-note quota-source', quotas.error || 'Moshi account snapshots · checked every minute · shared across projects'));
    $('quotas').replaceChildren(...panels);
  } catch (error) {
    const note = $('quotas').querySelector('.quota-source') || node('p', 'quota-note quota-source');
    note.textContent = 'Quota refresh unavailable · retrying in one minute. Any displayed snapshot may be out of date.';
    $('quotas').append(note);
  }
}
async function refresh() {
  if (busy) return;
  busy = true;
  const requestRevision = revision;
  try {
    const catalog = await get('/api/catalog');
    if (requestRevision !== revision) return;
    const params = new URLSearchParams(location.search);
    options($('project'), catalog.map(entry => entry.project), $('project').value || params.get('project') || catalog.at(-1)?.project);
    const project = catalog.find(entry => entry.project === $('project').value);
    options($('cycle'), project?.cycles || [], $('cycle').value || params.get('cycle'));
    if (!project) {
      $('board').replaceChildren(node('p', '', 'No cycles with issues yet. Create tickets to see them here.'));
      $('worker-state').textContent = 'No project selected';
      $('connection').textContent = 'Connected · no issues';
      return;
    }
    const query = new URLSearchParams({project: project.project, cycle: $('cycle').value});
    const board = await get(`/api/board?${query}`);
    if (requestRevision !== revision) return;
    render(board);
    history.replaceState(null, '', `/?${query}`);
    $('error').hidden = !board.warnings.length;
    $('error').textContent = board.warnings.join(' · ');
    $('connection').textContent = `● Live · updated ${new Date().toLocaleTimeString()}`;
  } catch (error) {
    $('error').hidden = false;
    $('error').textContent = `${error.message} Displayed status may be out of date.`;
    $('connection').textContent = 'Disconnected · retrying';
  } finally {
    busy = false;
    if (requestRevision !== revision) refresh();
  }
}
$('project').addEventListener('change', () => { $('cycle').replaceChildren(); revision++; refresh(); });
$('cycle').addEventListener('change', () => { revision++; refresh(); });
$('close').addEventListener('click', () => $('details').close());
$('details').addEventListener('click', event => { if (event.target === $('details') && event.offsetX < 0) $('details').close(); });
refresh();
refreshQuotas();
setInterval(refresh, 4000);
setInterval(refreshQuotas, 60000);
