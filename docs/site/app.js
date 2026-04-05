import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';

mermaid.initialize({
  startOnLoad: false,
  theme: 'default',
  securityLevel: 'loose',
  flowchart: { htmlLabels: true, curve: 'basis' },
});

// Route definitions. Each entry: file path (relative to server root) or a render function.
const routes = {
  'home':                   { file: null, title: 'Overview', render: renderHome },
  'architecture':           { file: '/docs/architecture.md', title: 'Architecture — System Views' },
  'harness-schema':         { file: '/docs/harness-schema.md', title: 'Harness Schema' },
  'factory-blueprint':      { file: '/factory-blueprint.md', title: 'Factory Blueprint' },
  'digital-workforce':      { file: '/Digital-Workforce-Platform-FINAL-v3.1.md', title: 'Digital Workforce Platform' },
  'handoff':                { file: '/HANDOFF.md', title: 'HANDOFF' },
  'pivot-plan':             { file: '/PIVOT-PLAN.md', title: 'Pivot Plan' },
  'sprint-plan':            { file: '/SPRINT-PLAN.md', title: 'Sprint Plan' },
  'orchestrator-prompt':    { file: '/ORCHESTRATOR-PROMPT.md', title: 'Orchestrator Prompt' },
  'claude-agent-sdk':       { file: '/docs/claude-agent-sdk-deep-dive.md', title: 'Agent SDK Deep Dive' },
  'requirements':           { file: '/REQUIREMENTS.md', title: 'Requirements' },
  'journal':                { file: '/JOURNAL.md', title: 'Journal' },
  'mechanic-soul':          { file: '/mechanic/config/SOUL.md', title: 'Mechanic — SOUL' },
  'mechanic-identity':      { file: '/mechanic/config/IDENTITY.md', title: 'Mechanic — IDENTITY' },
  'mechanic-agents':        { file: '/mechanic/config/AGENTS.md', title: 'Mechanic — AGENTS' },
  'mechanic-a-prompt':      { file: '/mechanics/mechanic-a-prompt.md', title: 'Mechanic A Prompt' },
  'mechanic-c-scout':       { file: '/mechanics/mechanic-c-scout-prompt.md', title: 'Mechanic C — The Scout' },
  'secret-injection':       { file: '/security/secret-injection.md', title: 'Secret Injection' },
  'self-modification-guard':{ file: '/security/self-modification-guard.md', title: 'Self-Modification Guard' },
  'claude-md':              { file: '/CLAUDE.md', title: 'Project Rules (CLAUDE.md)' },
};

// Configure marked: mermaid blocks become divs, other code blocks get highlighted.
const renderer = new marked.Renderer();
const originalCode = renderer.code.bind(renderer);
renderer.code = function(code, language) {
  // marked v12 passes {text, lang, escaped} as a single object
  if (typeof code === 'object' && code !== null) {
    const info = code;
    code = info.text;
    language = info.lang;
  }
  if (language === 'mermaid') {
    // Preserve raw mermaid source
    return `<div class="mermaid">${escapeHtml(code)}</div>`;
  }
  if (window.hljs) {
    try {
      const lang = language && hljs.getLanguage(language) ? language : null;
      const highlighted = lang
        ? hljs.highlight(code, { language: lang }).value
        : hljs.highlightAuto(code).value;
      return `<pre><code class="hljs language-${language || 'plaintext'}">${highlighted}</code></pre>`;
    } catch {}
  }
  return `<pre><code>${escapeHtml(code)}</code></pre>`;
};

marked.use({ renderer, breaks: false, gfm: true });

function escapeHtml(s) {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

async function loadRoute(routeName) {
  const route = routes[routeName] || routes['home'];
  const content = document.getElementById('content');

  document.title = `chat-force — ${route.title}`;

  if (route.render) {
    content.innerHTML = route.render();
  } else if (route.file) {
    content.innerHTML = '<p>Loading…</p>';
    try {
      const resp = await fetch(route.file);
      if (!resp.ok) throw new Error(`HTTP ${resp.status} for ${route.file}`);
      const md = await resp.text();
      const html = marked.parse(md);
      content.innerHTML = `<article>${html}</article>`;
      // Render any mermaid diagrams inside the loaded content
      try {
        await mermaid.run({ querySelector: '.mermaid' });
      } catch (e) {
        console.warn('mermaid render error', e);
      }
    } catch (e) {
      content.innerHTML = `<div class="error">Failed to load <code>${route.file}</code>: ${e.message}</div>`;
    }
  }

  // Update active sidebar link
  document.querySelectorAll('nav a').forEach(a => {
    a.classList.toggle('active', a.getAttribute('href') === '#' + routeName);
  });

  // Scroll content to top
  content.scrollTop = 0;
}

function renderHome() {
  return `
    <div class="home">
      <h1>chat-force</h1>
      <p class="subtitle">A tuning harness for frontier intelligence, delivered as a branded bot per customer.</p>

      <p class="big-quote">"Vibe Code up front. Mechanic in the back."</p>

      <section>
        <h2>Mission</h2>
        <p>Get chat-force to the point where a branded Leo can be handed to a real customer workspace
        and Travis can sleep at night. The system does real work, recovers from its own mistakes, and
        pages you before the customer notices anything is wrong.</p>
      </section>

      <section>
        <h2>The Core Insight</h2>
        <p>Prototyping is human-speed, creative, any-means-necessary. Quality is enforced mechanically,
        separately, after the fact. Every caught mistake becomes a permanent improvement to that customer's
        harness. <strong>The mechanic log is the compounding asset.</strong></p>
      </section>

      <section>
        <h2>The Split</h2>
        <div class="split">
          <div>
            <h3>Factory Engine (chat-force)</h3>
            <p>Shared code. One copy per host. Universal logic: pipeline orchestration, Worker/Mechanic
            protocol, Slack listener, IPC, observability, tests, CI. Identical for every customer.</p>
            <p><strong>Mechanic = HOW.</strong></p>
          </div>
          <div>
            <h3>Customer Harness (harness-&lt;slug&gt;)</h3>
            <p>One per customer. Contains mission, brand, eval criteria, skills (grown by factory),
            brand assets, mechanic log. Half customer-authored, half factory-grown.</p>
            <p><strong>Eval = WHAT.</strong></p>
          </div>
        </div>
      </section>

      <section>
        <h2>Principles</h2>
        <div class="principles">
          <ol>
            <li><strong>Vibes up front, mechanics behind.</strong> The two loops are sequential, not opposed. Creativity and quality aren't in conflict — they're separated in time.</li>
            <li><strong>Mechanical verification at the quality layer.</strong> Every invariant that matters enforced by code or test.</li>
            <li><strong>Root cause every issue.</strong> No workarounds that create debt.</li>
            <li><strong>Fail loud, never silent.</strong> A crash you can see beats a wrong answer you can't.</li>
            <li><strong>Hostile input by default.</strong> Slack user, LLM output, container — all adversarial until proven otherwise.</li>
            <li><strong>Customer trust is the product.</strong> Slow and never-embarrassing beats fast and occasionally-wrong.</li>
            <li><strong>Architect for change.</strong> LLM will be modifying this weekly. Readability and testability beat cleverness.</li>
          </ol>
        </div>
      </section>

      <section>
        <h2>First Customer Wave</h2>
        <ul class="customer-list">
          <li>harness-black-tie — Black Tie Components</li>
          <li>harness-aaa-pure-water — AAA Pure Water</li>
          <li>harness-mailbox-money — Mailbox Money</li>
          <li>harness-usaf — USAF</li>
          <li>harness-travis-personal — personal assistant (later)</li>
        </ul>
      </section>

      <section>
        <h2>Start Reading</h2>
        <p>Recommended order if this is your first time:</p>
        <ol>
          <li><a href="#architecture">Architecture — 4 system views</a> (start here to see the shape of things)</li>
          <li><a href="#factory-blueprint">Factory Blueprint</a> (the vision document)</li>
          <li><a href="#harness-schema">Harness Schema</a> (the structural contract)</li>
          <li><a href="#handoff">HANDOFF</a> (current state of the codebase)</li>
          <li><a href="#claude-agent-sdk">Agent SDK Deep Dive</a> (reference for the runtime)</li>
        </ol>
      </section>
    </div>
  `;
}

// Router
window.addEventListener('hashchange', () => {
  const route = window.location.hash.slice(1) || 'home';
  loadRoute(route);
});

// Initial load
const initial = window.location.hash.slice(1) || 'home';
loadRoute(initial);
