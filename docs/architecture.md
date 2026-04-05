# chat-force Architecture

Four views of the same system. Read in order — each builds on the previous.

---

## View 1 — Deployment Topology (where things physically live)

One host. One Slack workspace. N bots, each as a separate process. N harnesses on disk.

```mermaid
flowchart TB
  subgraph Host["Host — Mac Mini / VPS (one machine for all customers initially)"]
    direction TB
    Engine["chat-force engine binary<br/>(shared, installed once)"]
    subgraph Units["systemd units"]
      direction LR
      U1["chat-force@black-tie.service"]
      U2["chat-force@mailbox-money.service"]
      U3["chat-force@aaa-pure-water.service"]
      U4["chat-force@usaf.service"]
    end
    subgraph Store["/var/lib/chat-force/harnesses/"]
      direction LR
      HR1["harness-black-tie/"]
      HR2["harness-mailbox-money/"]
      HR3["harness-aaa-pure-water/"]
      HR4["harness-usaf/"]
    end
    U1 -.->|uses| Engine
    U2 -.->|uses| Engine
    U3 -.->|uses| Engine
    U4 -.->|uses| Engine
    U1 -->|HARNESS_PATH| HR1
    U2 -->|HARNESS_PATH| HR2
    U3 -->|HARNESS_PATH| HR3
    U4 -->|HARNESS_PATH| HR4
  end

  Doppler[("Doppler<br/>one config per customer")]
  subgraph TravisSlack["Slack: Travis Hendrickson workspace"]
    direction TB
    subgraph Apps["Slack Apps (one per customer)"]
      A1["BlackTie"]
      A2["Mailbox"]
      A3["Aqua"]
      A4["USAF"]
    end
    subgraph Channels["Channels per customer"]
      C1["#black-tie-intake<br/>#black-tie-floor<br/>#black-tie-mechanic-log<br/>#black-tie-assets"]
      C2["#mailbox-money-*"]
      C3["#aaa-pure-water-*"]
      C4["#usaf-*"]
    end
    A1 -.-> C1
    A2 -.-> C2
    A3 -.-> C3
    A4 -.-> C4
  end

  U1 <-->|socket mode| A1
  U2 <-->|socket mode| A2
  U3 <-->|socket mode| A3
  U4 <-->|socket mode| A4

  U1 -->|secrets| Doppler
  U2 -->|secrets| Doppler
  U3 -->|secrets| Doppler
  U4 -->|secrets| Doppler
```

**Mental model:** one binary, many units. Adding customer #5 = create harness repo, add systemd unit, add Doppler config, create Slack App. No code changes.

---

## View 2 — Engine vs Harness (what lives where)

This is the single most important split. Everything in the engine is shared across all customers. Everything in the harness is that customer's alone. Get this wrong and nothing else works.

```mermaid
flowchart LR
  subgraph Engine["FACTORY ENGINE — chat-force repo (ONE copy, shared by all customers)"]
    direction TB
    E1["pipeline/<br/>session manager<br/>worker manager<br/>mechanic manager<br/>PR creator<br/>slack listener"]
    E2["worker/<br/>Dockerfile<br/>entrypoint.py"]
    E3["mechanic/config/<br/>how-to-review logic<br/>(universal)"]
    E4["tests/<br/>mechanical checks<br/>CI"]
    E5["HarnessLoader<br/>(reads + validates)"]
  end

  subgraph Harness["CUSTOMER HARNESS — harness-&lt;slug&gt; repo (ONE per customer)"]
    direction TB
    H1["workspace.yaml<br/>bot identity · git identity<br/>channels · access · limits<br/>secrets refs · deliverables"]
    H2["identity/<br/>mission.md<br/>brand.md<br/>avatar.md<br/>never-list.md<br/>bot-persona.md"]
    H3["eval/criteria.yaml<br/>WHAT good looks like<br/>(customer's definition)"]
    H4["skills/<br/>grown by the factory<br/>over time"]
    H5["brand-assets/<br/>logos, URLs, references,<br/>past campaigns"]
    H6["mechanic-log/<br/>structured fix log<br/>(the moat — compounds)"]
  end

  Engine -->|"HARNESS_PATH env var<br/>points engine at one harness"| Harness
```

**The two halves of review:**
- **Eval** = WHAT the customer wants (harness, customer-authored)
- **Mechanic** = HOW to build and review it (engine, universal)

**The two sources of harness content:**
- **Customer-authored** (mission, brand, avatar, eval criteria) — rarely changes
- **Factory-grown** (skills, mechanic-log entries, refined prompts) — grows every session

---

## View 3 — The Two Loops (Vibe Code + Mechanic)

The core insight of the whole system. Vibes allowed in front, mechanics enforced in back.

```mermaid
flowchart TB
  subgraph Vibe["VIBE CODE — Front of House (fast, human-in-loop, any-means-necessary)"]
    direction LR
    V1["Customer or Anna<br/>posts job in<br/>#intake"]
    V2["Prototyper + Bot<br/>collaborate in<br/>#factory-floor<br/>draft · iterate · ship"]
    V3["Deliverable lands<br/>where it lives<br/>(Google Doc, Meta ad,<br/>landing page, vault)"]
    V1 --> V2 --> V3
  end

  subgraph Mech["MECHANIC — Back of House (rigorous, slow, compounding)"]
    direction LR
    M1["Mechanic Agent<br/>analyzes session<br/>(tool log, friction,<br/>patterns, gaps)"]
    M2["Structured fix<br/>proposal posted to<br/>#mechanic-log"]
    M3["Human Mechanic<br/>reviews, edits,<br/>approves in Slack"]
    M4["Fix installs into<br/>harness skills/ or<br/>eval/ or persona<br/>(via PR)"]
    M1 --> M2 --> M3 --> M4
  end

  V2 -.->|"session transcript<br/>tool log<br/>friction points<br/>usage data"| M1
  M4 -.->|"next run<br/>is tighter"| V2
```

**Three distinct 'mechanic' roles — do not conflate:**

| Role | What it does | Where it lives |
|------|--------------|----------------|
| **Automated Eval** | Runs mechanical checks (regex, URL-check, LLM-judge) on every output before it ships | Engine code + `eval/criteria.yaml` in harness |
| **Mechanic Agent** | The AI that analyzes sessions and *proposes* fixes | Engine (`mechanic/config/`) + uses harness eval criteria as input |
| **Human Mechanic (you)** | Reviews proposed fixes in `#mechanic-log`, approves installations | You, in Slack |

Only the Human Mechanic can install fixes. The Agent proposes, never commits.

---

## View 4 — One Session End-to-End

A single message from Slack through to deliverable, with the mechanic-log entry that comes after.

```mermaid
sequenceDiagram
  autonumber
  participant C as Customer/Anna
  participant I as "#intake"
  participant E as Engine Listener
  participant F as "#factory-floor"
  participant W as Worker Container
  participant H as Harness Files
  participant D as Deliverable Store
  participant MA as Mechanic Agent
  participant ML as "#mechanic-log"
  participant HM as Human Mechanic

  C->>I: "Need 5 LinkedIn posts"
  I->>E: message event
  E->>H: load identity + eval + skills
  E->>F: open session, post status
  E->>W: start container, mount harness
  W->>F: drafts, progress updates
  F->>C: deliverable shipped
  W->>D: final asset lands here

  Note over E,MA: session closes (idle timeout or explicit)

  E->>MA: transcript + tool log + eval criteria
  MA->>ML: structured fix proposal
  ML->>HM: notification in Slack
  HM->>H: approve + merge via PR
  H-->>W: next session benefits
```

**Key property:** the deliverable flows on the left (customer side, fast). The fix flows on the right (factory side, compounding). They never block each other.

---

## Summary — Three Principles This Architecture Enforces

1. **Vibes up front, mechanics behind.** Prototyping is human-speed and freeform. Quality is enforced mechanically, separately, after the fact.

2. **Engine is universal, harness is unique.** One engine serves N customers. Every customer has exactly one harness. Knowledge transfer between customers is a manual operation by the human mechanic, not an engine feature.

3. **Changes compound in the harness, not the engine.** Every caught mistake becomes a permanent improvement to that customer's harness. The engine only changes when you improve the factory itself — not on a per-customer basis.
