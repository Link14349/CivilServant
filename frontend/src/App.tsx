import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import {
  actOnDocument,
  cancelEntry,
  createGame,
  finishDay,
  finishScene,
  generateMeetingSpeech,
  getConfig,
  loadGame,
  requestDraft,
  scheduleEntry,
  sendPlayerSpeech,
  startConversation,
  startFieldVisit,
  startMeeting,
  submitDocument,
  validateCredentials,
  voteMeeting,
} from "./api";
import type {
  Actor,
  AppConfig,
  Credentials,
  DiscussionMode,
  DocumentItem,
  Game,
  MeetingType,
  ScheduleKind,
} from "./types";

const STORAGE = {
  sessionKey: "civilservant.deepseek.session-key",
  localKey: "civilservant.deepseek.local-key",
  model: "civilservant.deepseek.model",
  apiBase: "civilservant.deepseek.api-base",
  liveGame: "civilservant.game.live",
  templateGame: "civilservant.game.template",
};

type DeskTab = "briefing" | "documents" | "calendar" | "activity";
type ActionPanel = "talk" | "meeting" | "field" | "schedule" | "draft" | null;

export default function App() {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [credentials, setCredentials] = useState<Credentials | null>(null);
  const [bootError, setBootError] = useState("");

  useEffect(() => {
    getConfig().then(setConfig).catch((error: Error) => setBootError(error.message));
  }, []);

  if (bootError) return <CenteredMessage title="无法启动" message={bootError} />;
  if (!config) return <CenteredMessage title="正在整理案头材料" message="正在连接本机后端……" loading />;
  if (!credentials) return <KeyGate config={config} onEnter={setCredentials} />;
  return <Workspace credentials={credentials} onChangeCredentials={() => setCredentials(null)} />;
}

function KeyGate({ config, onEnter }: { config: AppConfig; onEnter: (value: Credentials) => void }) {
  const localKey = localStorage.getItem(STORAGE.localKey) ?? "";
  const sessionKey = sessionStorage.getItem(STORAGE.sessionKey) ?? "";
  const [apiKey, setApiKey] = useState(localKey || sessionKey);
  const [apiBase, setApiBase] = useState(localStorage.getItem(STORAGE.apiBase) ?? config.default_api_base);
  const [model, setModel] = useState(localStorage.getItem(STORAGE.model) ?? config.default_model);
  const [remember, setRemember] = useState(Boolean(localKey));
  const [validating, setValidating] = useState(false);
  const [error, setError] = useState("");

  async function enterLive() {
    setError("");
    if (!apiKey.trim()) {
      setError("请输入 DeepSeek API Key；也可以先进入模板调试模式。");
      return;
    }
    const next: Credentials = {
      mode: "live",
      apiKey: apiKey.trim(),
      apiBase: apiBase.trim(),
      model: model.trim(),
      remember,
    };
    setValidating(true);
    try {
      await validateCredentials(next);
      persistCredentials(next);
      onEnter(next);
    } catch (caught) {
      setError(errorText(caught, "验证失败，请检查模型设置。"));
    } finally {
      setValidating(false);
    }
  }

  function enterTemplate() {
    onEnter({
      mode: "template",
      apiKey: "",
      apiBase: apiBase.trim() || config.default_api_base,
      model: model.trim() || config.default_model,
      remember: false,
    });
  }

  return (
    <main className="gate-shell">
      <section className="gate-intro" aria-labelledby="gate-title">
        <div className="seal" aria-hidden="true">岚</div>
        <p className="eyebrow">虚构地方治理模拟</p>
        <h1 id="gate-title">岚州 · 领导工作台</h1>
        <p className="gate-lead">
          每天从晨报开始。见谁、开什么会、去哪里看，由你安排；材料和表态只是各自视角，后果会在时间中逐步显现。
        </p>
        <div className="gate-principles"><span>有限精力</span><span>信息隔离</span><span>授权执行</span><span>延迟后果</span></div>
      </section>
      <section className="key-card" aria-labelledby="key-title">
        <p className="card-kicker">进入工作台</p>
        <h2 id="key-title">连接 DeepSeek</h2>
        <p className="muted">Key 只传给本机后端完成模型请求，不进入游戏存档或服务端日志。</p>
        <label className="field-label" htmlFor="api-key">DeepSeek API Key</label>
        <input id="api-key" className="text-input" type="password" autoComplete="off" placeholder="sk-…" value={apiKey} onChange={(event) => setApiKey(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") void enterLive(); }} />
        <label className="remember-row">
          <input type="checkbox" checked={remember} onChange={(event) => setRemember(event.target.checked)} />
          <span>在这台浏览器上记住 Key</span>
        </label>
        <p className="storage-note">{remember ? "保存到 localStorage，直到主动清除。" : "仅保存到 sessionStorage，关闭浏览器后清除。"}</p>
        <details className="advanced-settings">
          <summary>高级模型设置</summary>
          <label className="field-label" htmlFor="model-name">模型</label>
          <input id="model-name" className="text-input" value={model} onChange={(event) => setModel(event.target.value)} />
          <label className="field-label" htmlFor="api-base">API Base URL</label>
          <input id="api-base" className="text-input" value={apiBase} onChange={(event) => setApiBase(event.target.value)} />
        </details>
        {error && <div className="error-banner" role="alert">{error}</div>}
        <button className="primary-button full" onClick={() => void enterLive()} disabled={validating}>{validating ? "正在验证模型…" : "验证并进入"}</button>
        <button className="text-button full" onClick={enterTemplate} disabled={validating}>没有 Key？进入模板调试模式</button>
      </section>
    </main>
  );
}

function Workspace({ credentials, onChangeCredentials }: { credentials: Credentials; onChangeCredentials: () => void }) {
  const [game, setGame] = useState<Game | null>(null);
  const [restoring, setRestoring] = useState(true);
  const [restoreError, setRestoreError] = useState("");
  const gameStorageKey = credentials.mode === "live" ? STORAGE.liveGame : STORAGE.templateGame;

  useEffect(() => {
    const gameId = localStorage.getItem(gameStorageKey);
    if (!gameId) {
      setRestoring(false);
      return;
    }
    loadGame(gameId)
      .then(setGame)
      .catch((error: Error) => {
        localStorage.removeItem(gameStorageKey);
        setRestoreError(`原存档未能载入：${error.message}`);
      })
      .finally(() => setRestoring(false));
  }, [gameStorageKey]);

  function rememberGame(next: Game) {
    localStorage.setItem(gameStorageKey, next.id);
    setGame(next);
  }

  if (restoring) return <CenteredMessage title="正在调取存档" message="请稍候……" loading />;
  if (!game) return <GameSetup credentials={credentials} initialError={restoreError} onStarted={rememberGame} onChangeCredentials={onChangeCredentials} />;
  return (
    <GameBoard
      game={game}
      credentials={credentials}
      onGameChange={rememberGame}
      onNewGame={() => { localStorage.removeItem(gameStorageKey); setGame(null); }}
      onChangeCredentials={onChangeCredentials}
    />
  );
}

function GameSetup({ credentials, initialError, onStarted, onChangeCredentials }: {
  credentials: Credentials;
  initialError: string;
  onStarted: (game: Game) => void;
  onChangeCredentials: () => void;
}) {
  const [playerName, setPlayerName] = useState("林砚");
  const [background, setBackground] = useState("general");
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState(initialError);

  async function start() {
    if (!playerName.trim()) { setError("请填写主角姓名。"); return; }
    setStarting(true);
    setError("");
    try {
      onStarted(await createGame(playerName.trim(), background, credentials.mode, credentials.model, credentials.apiBase));
    } catch (caught) {
      setError(errorText(caught, "无法创建游戏。"));
    } finally {
      setStarting(false);
    }
  }

  return (
    <main className="setup-shell">
      <header className="setup-header">
        <div><p className="eyebrow">开放式按日模拟</p><h1>岚州市委书记</h1></div>
        <button className="ghost-button" onClick={onChangeCredentials}>模型设置</button>
      </header>
      <section className="setup-grid">
        <article className="paper-card briefing-card">
          <p className="card-kicker">任前简报</p>
          <h2>工作不会按剧本排队发生</h2>
          <p>产业整改、财政约束、防汛准备和干部协同同时存在。你每天有有限行动点，可以谈话、开会、调研或向上汇报；批阅文件不耗行动点。</p>
          <p>属下只知道其渠道允许知道的情况，也会依据职责、立场和风险判断决定说什么、做什么。正式决定仍须经过相应程序。</p>
          <div className="scenario-facts"><div><strong>每日</strong><span>动态晨报</span></div><div><strong>16 人</strong><span>独立角色</span></div><div><strong>开放</strong><span>没有固定回合</span></div></div>
        </article>
        <article className="paper-card identity-card">
          <p className="card-kicker">任命信息</p>
          <label className="field-label" htmlFor="player-name">主角姓名</label>
          <input id="player-name" className="text-input large" value={playerName} maxLength={20} onChange={(event) => setPlayerName(event.target.value)} />
          <label className="field-label" htmlFor="background">主要工作经历</label>
          <select id="background" className="text-input" value={background} onChange={(event) => setBackground(event.target.value)}>
            <option value="general">省级综合部门</option><option value="industry">产业与经济工作</option><option value="county">县区主政经历</option><option value="political_legal">政法与治理工作</option>
          </select>
          <dl className="identity-list"><div><dt>职务</dt><dd>岚州市委书记</dd></div><div><dt>本地基础</dt><dd>较弱，仍在建立信息渠道</dd></div><div><dt>运行模式</dt><dd>{credentials.mode === "live" ? credentials.model : "模板调试"}</dd></div></dl>
          {error && <div className="error-banner" role="alert">{error}</div>}
          <button className="primary-button full" onClick={() => void start()} disabled={starting}>{starting ? "正在整理第一份晨报…" : "到任并打开晨报"}</button>
        </article>
      </section>
    </main>
  );
}

function GameBoard({ game, credentials, onGameChange, onNewGame, onChangeCredentials }: {
  game: Game;
  credentials: Credentials;
  onGameChange: (game: Game) => void;
  onNewGame: () => void;
  onChangeCredentials: () => void;
}) {
  const [tab, setTab] = useState<DeskTab>("briefing");
  const [panel, setPanel] = useState<ActionPanel>(null);
  const [preferredActorId, setPreferredActorId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (game.active_scene?.generation.status !== "thinking") return;
    const timer = window.setInterval(() => {
      loadGame(game.id).then(onGameChange).catch(() => undefined);
    }, 650);
    return () => window.clearInterval(timer);
  }, [game.id, game.active_scene?.generation.status, onGameChange]);

  async function mutate(operation: () => Promise<Game>) {
    setBusy(true);
    setError("");
    try {
      onGameChange(await operation());
      setPanel(null);
    } catch (caught) {
      setError(errorText(caught, "操作未能完成。"));
    } finally {
      setBusy(false);
    }
  }

  const dueNow = game.calendar.filter((item) => item.date === game.current_date && item.status !== "completed" && item.status !== "canceled");
  return (
    <div className="workbench-shell">
      <header className="topbar">
        <div className="brand-lockup"><div className="mini-seal">岚</div><div><span className="brand-title">领导工作台</span><span className="brand-subtitle">{game.player_name} · {game.role_title}</span></div></div>
        <div className="topbar-date"><strong>{formatDate(game.current_date)}</strong><span>到任第 {game.day_number} 天</span></div>
        <div className="topbar-meta"><span className={`mode-badge ${game.mode}`}>{game.mode === "live" ? game.model : "模板调试"}</span><button className="topbar-button" onClick={onChangeCredentials}>模型设置</button><button className="topbar-button" onClick={() => { if (window.confirm("确定离开当前存档并新建游戏？")) onNewGame(); }}>新游戏</button></div>
      </header>

      <div className="daily-layout">
        <aside className="desk-nav">
          <div className="nav-label">今日案头</div>
          <DeskNavButton active={tab === "briefing"} label="晨报" count={game.briefing.length} onClick={() => setTab("briefing")} />
          <DeskNavButton active={tab === "documents"} label="文件" count={game.documents.filter((item) => item.status !== "archived").length} onClick={() => setTab("documents")} />
          <DeskNavButton active={tab === "calendar"} label="日程" count={dueNow.length} onClick={() => setTab("calendar")} />
          <DeskNavButton active={tab === "activity"} label="工作记录" count={game.activity.length} onClick={() => setTab("activity")} />
          <div className="nav-metrics">
            <div className="nav-label">局势指标</div>
            {game.metrics.map((metric) => <div className="mini-metric" key={metric.id}><span>{metric.label}</span><b className={!metric.higher_is_better && metric.value > 60 ? "risk" : ""}>{metric.value}</b></div>)}
          </div>
          <p className="fiction-note">人物、地区、企业和数字均为虚构。</p>
        </aside>

        <main className="daily-main">
          {error && <div className="error-banner" role="alert">{error}</div>}
          {game.notifications.slice(-2).map((item) => <div className={`notification ${item.tone}`} key={item.id}><strong>{item.title}</strong><span>{item.detail}</span></div>)}
          {game.active_scene ? (
            <SceneView game={game} credentials={credentials} busy={busy} onMutate={mutate} />
          ) : (
            <>
              {tab === "briefing" && <BriefingDesk game={game} onOpenDocument={() => setTab("documents")} />}
              {tab === "documents" && <DocumentDesk game={game} credentials={credentials} busy={busy} onMutate={mutate} />}
              {tab === "calendar" && <CalendarDesk game={game} credentials={credentials} busy={busy} onMutate={mutate} onAdd={() => setPanel("schedule")} />}
              {tab === "activity" && <ActivityDesk game={game} />}
            </>
          )}
        </main>

        <aside className="action-rail">
          <section className="action-budget">
            <div><span>今日行动点</span><strong>{game.action_budget.remaining}<small> / {game.action_budget.total}</small></strong></div>
            <div className="ap-track"><span style={{ width: `${game.action_budget.total ? (game.action_budget.remaining / game.action_budget.total) * 100 : 0}%` }} /></div>
            {game.action_budget.reserved_today > 0 && <p>今日另有 {game.action_budget.reserved_today} 点预定日程待执行</p>}
          </section>
          {!game.active_scene && (
            <section className="action-menu">
              <div className="nav-label">安排工作</div>
              <ActionButton label="找人谈话" note="1 点" disabled={game.action_budget.remaining < 1} onClick={() => { setPreferredActorId(null); setPanel("talk"); }} />
              <ActionButton label="召开会议" note="2 点" disabled={game.action_budget.remaining < 2} onClick={() => setPanel("meeting")} />
              <ActionButton label="现场调研" note="2 点" disabled={game.action_budget.remaining < 2} onClick={() => setPanel("field")} />
              <ActionButton label="预定日程" note="将来扣点" onClick={() => setPanel("schedule")} />
              <ActionButton label="交办文稿" note="不耗点" onClick={() => setPanel("draft")} />
            </section>
          )}
          <section className="actor-directory">
            <div className="nav-label">联系人</div>
            {game.actors.slice(0, 9).map((actor) => <button key={actor.id} disabled={Boolean(game.active_scene) || game.action_budget.remaining < 1} onClick={() => { setPreferredActorId(actor.id); setPanel("talk"); }} title={`${actor.public_position} ${actor.known_note}`}><span>{actor.name.slice(-1)}</span><div><strong>{actor.name}</strong><small>{actor.title}</small></div><em>{actor.relation}</em></button>)}
          </section>
          {!game.active_scene && <button className="end-day-button" disabled={busy} onClick={() => void mutate(() => finishDay(game, credentials))}>结束今天并推进</button>}
        </aside>
      </div>
      {panel && !game.active_scene && <ActionDrawer panel={panel} initialActorId={preferredActorId} game={game} credentials={credentials} busy={busy} onClose={() => setPanel(null)} onMutate={mutate} />}
    </div>
  );
}

function BriefingDesk({ game, onOpenDocument }: { game: Game; onOpenDocument: () => void }) {
  return (
    <>
      <DeskHeading kicker="每日晨报" title={`${formatDate(game.current_date)} · 需要你留意的事`} detail="晨报汇集昨日局势、下级报告、请示和日程提醒；来源不同，可靠程度也不同。" />
      <section className="brief-list">
        {game.briefing.map((item, index) => <article className={`brief-item urgency-${item.urgency}`} key={item.id}><span className="brief-index">{String(index + 1).padStart(2, "0")}</span><div><div className="brief-meta"><b>{briefCategory(item.category)}</b><span>{item.source}</span></div><h2>{item.headline}</h2><p>{item.summary}</p>{item.document_id && <button className="inline-button" onClick={onOpenDocument}>打开相关文件</button>}</div></article>)}
      </section>
      <section className="issue-board"><div className="section-heading"><h2>持续议题</h2><span>{game.issues.length} 项</span></div><div className="issue-grid">{game.issues.map((issue) => <article key={issue.id}><span className={`pressure ${issue.pressure}`}>{pressureLabel(issue.pressure)}</span><h3>{issue.title}</h3><p>{issue.summary}</p><small>{issue.known_status}</small></article>)}</div></section>
    </>
  );
}

function DocumentDesk({ game, credentials, busy, onMutate }: { game: Game; credentials: Credentials; busy: boolean; onMutate: (operation: () => Promise<Game>) => Promise<void> }) {
  const [selectedId, setSelectedId] = useState(game.documents[0]?.id ?? "");
  const selected = game.documents.find((item) => item.id === selectedId) ?? game.documents[0];
  const [note, setNote] = useState("");
  const [recipient, setRecipient] = useState("secretary_general");

  return (
    <>
      <DeskHeading kicker="文件流转" title="批阅、转办与向上报送" detail="批阅文件不消耗行动点。你可以批注、退回、转办，或将一份已经形成的材料直接报送上级。" />
      <div className="document-layout">
        <div className="document-list">{game.documents.map((document) => <button className={selected?.id === document.id ? "active" : ""} key={document.id} onClick={() => { setSelectedId(document.id); setNote(""); }}><span>{document.author_label} · {document.created_date}</span><strong>{document.title}</strong><small>{documentStatus(document.status)}</small></button>)}</div>
        {selected ? <DocumentReader document={selected} actors={game.actors} note={note} recipient={recipient} busy={busy} onNote={setNote} onRecipient={setRecipient} onAct={(operation) => onMutate(() => actOnDocument(game, credentials, selected.id, operation, note, recipient))} onSubmit={() => onMutate(() => submitDocument(game, credentials, selected.id, "superior", note))} /> : <div className="empty-card">当前没有呈阅文件。</div>}
      </div>
    </>
  );
}

function DocumentReader({ document, actors, note, recipient, busy, onNote, onRecipient, onAct, onSubmit }: {
  document: DocumentItem;
  actors: Actor[];
  note: string;
  recipient: string;
  busy: boolean;
  onNote: (value: string) => void;
  onRecipient: (value: string) => void;
  onAct: (operation: "annotate" | "return" | "forward" | "archive") => Promise<void>;
  onSubmit: () => Promise<void>;
}) {
  return <article className="document-reader"><header><p>{document.confidentiality} · {document.document_type}</p><h2>{document.title}</h2><span>{document.author_label} · 第 {document.version} 版</span></header><div className="document-summary">摘要：{document.summary}</div><div className="document-body">{document.content}</div><div className="formal-effect"><strong>当前效力</strong><span>{document.formal_effect}</span></div>{document.source_document_ids.length > 0 && <p className="lineage">引用材料：{document.source_document_ids.join("、")}</p>}{document.annotations.map((item) => <p className="annotation" key={item}>{item}</p>)}<label className="field-label" htmlFor="document-note">批示或报送说明</label><textarea id="document-note" rows={3} value={note} onChange={(event) => onNote(event.target.value)} placeholder="例如：请财政局核对资金来源，三日内报送。" /><div className="document-actions"><button disabled={busy || !note.trim()} onClick={() => void onAct("annotate")}>批注</button><button disabled={busy || !note.trim()} onClick={() => void onAct("return")}>退回修改</button><select value={recipient} onChange={(event) => onRecipient(event.target.value)}>{actors.filter((actor) => actor.id !== "superior").map((actor) => <option key={actor.id} value={actor.id}>{actor.name} · {actor.title}</option>)}</select><button disabled={busy} onClick={() => void onAct("forward")}>转办</button><button className="submit-up" disabled={busy} onClick={() => void onSubmit()}>报送省委书记</button></div></article>;
}

function CalendarDesk({ game, credentials, busy, onMutate, onAdd }: { game: Game; credentials: Credentials; busy: boolean; onMutate: (operation: () => Promise<Game>) => Promise<void>; onAdd: () => void }) {
  const entries = [...game.calendar].sort((a, b) => a.date.localeCompare(b.date));
  return <><DeskHeading kicker="日程管理" title="今天与以后" detail="预定事项在执行当天扣除行动点；上级也可能临时要求汇报，并占用当天精力。" action={<button className="ghost-button" onClick={onAdd}>添加日程</button>} /><div className="calendar-list">{entries.length === 0 ? <div className="empty-card">目前没有日程。</div> : entries.map((entry) => <article key={entry.id}><time>{formatDate(entry.date)}</time><div><span>{scheduleKind(entry.kind)} · {entry.action_cost} 点</span><h3>{entry.title}</h3><p>{entry.participant_labels.join("、") || entry.location_label || "待确定"}</p><small>{entry.source} · {calendarStatus(entry.status)}</small></div>{entry.status === "scheduled" && !entry.mandatory && <button disabled={busy} onClick={() => void onMutate(() => cancelEntry(game, credentials, entry.id))}>取消</button>}</article>)}</div></>;
}

function ActivityDesk({ game }: { game: Game }) {
  return <><DeskHeading kicker="工作记录" title="已经发生的事" detail="这里只显示玩家可以看到的工作痕迹；人物私下联络和未被你获知的行动不会自动出现。" /><div className="activity-timeline">{[...game.activity].reverse().map((item) => <article key={item.id}><time>{item.date}</time><div><span>{item.kind}</span><h3>{item.title}</h3><p>{item.summary}</p></div></article>)}</div>{game.pending_tasks.length > 0 && <section className="pending-box"><h2>等待中的文稿</h2>{game.pending_tasks.map((item) => <p key={item}>{item}</p>)}</section>}</>;
}

function SceneView({ game, credentials, busy, onMutate }: { game: Game; credentials: Credentials; busy: boolean; onMutate: (operation: () => Promise<Game>) => Promise<void> }) {
  const scene = game.active_scene!;
  const [speech, setSpeech] = useState("");
  const [resolution, setResolution] = useState("");
  const isMeeting = scene.kind === "meeting";
  const thinking = scene.generation.status === "thinking";

  async function speak() {
    if (!speech.trim()) return;
    const text = speech.trim();
    setSpeech("");
    await onMutate(() => sendPlayerSpeech(game, credentials, text));
  }

  return <section className="scene-shell"><header className="scene-header"><div><p className="section-kicker">{sceneKind(scene.kind)} · 已消耗 {scene.action_cost} 点</p><h1>{scene.title}</h1>{scene.agenda && <span>议题：{scene.agenda}</span>}</div>{thinking && <div className="thinking"><i /><span>{scene.generation.message}</span></div>}</header><div className="participant-strip">{scene.participants.map((item) => <span key={item.actor_id}>{item.name}<small>{item.attendance_role === "chair" ? "主持" : item.can_vote ? "成员" : "列席"}</small></span>)}</div><div className="transcript" aria-live="polite">{scene.transcript.map((turn) => <article className={turn.speaker_type} key={turn.id}><div>{turn.speaker_name}</div><p>{turn.text}</p></article>)}</div>{scene.generation.status === "canceled" && <p className="generation-note">{scene.generation.message}</p>}{isMeeting && <div className="meeting-controls"><span>{scene.discussion_mode === "free" ? "自由磋商：参会者会自行判断是否发言" : "主持磋商：由你点名发言"}</span>{scene.discussion_mode === "free" ? <button disabled={busy || thinking} onClick={() => void onMutate(() => generateMeetingSpeech(game, credentials))}>让会议继续</button> : <div className="nominate-list">{scene.participants.filter((item) => item.actor_id !== "player").map((item) => <button disabled={busy || thinking} key={item.actor_id} onClick={() => void onMutate(() => generateMeetingSpeech(game, credentials, item.actor_id))}>请{item.name}发言</button>)}</div>}</div>}<div className="speech-box"><label htmlFor="player-speech">你的发言或追问</label><textarea id="player-speech" rows={4} value={speech} maxLength={2400} onChange={(event) => setSpeech(event.target.value)} placeholder={thinking ? "你可以随时发言，正在生成的 NPC 发言会被中断。" : "可以追问事实、表明目标、划定红线或作出交办。"} /><button className="primary-button" disabled={busy || !speech.trim()} onClick={() => void speak()}>{thinking ? "打断并发言" : "发言"}</button></div>{scene.can_vote && <div className="vote-box"><label htmlFor="resolution">拟表决事项</label><textarea id="resolution" rows={3} value={resolution} onChange={(event) => setResolution(event.target.value)} placeholder="写清需要集体表决的决定。" />{scene.vote_result ? <p>{scene.vote_result}</p> : <button disabled={busy || !resolution.trim() || thinking} onClick={() => void onMutate(() => voteMeeting(game, credentials, resolution.trim()))}>提请表决</button>}</div>}<div className="scene-footer"><span>结束后，人物会依据会谈内容形成记忆，并可能联络他人、准备材料或提出后续行动。</span><button className="ghost-button" disabled={busy || thinking} onClick={() => void onMutate(() => finishScene(game, credentials, resolution.trim()))}>结束并结算</button></div></section>;
}

function ActionDrawer({ panel, initialActorId, game, credentials, busy, onClose, onMutate }: { panel: Exclude<ActionPanel, null>; initialActorId: string | null; game: Game; credentials: Credentials; busy: boolean; onClose: () => void; onMutate: (operation: () => Promise<Game>) => Promise<void> }) {
  const [actorId, setActorId] = useState(initialActorId ?? game.actors[0]?.id ?? "mayor");
  const [meetingType, setMeetingType] = useState<MeetingType>("coordination");
  const [discussionMode, setDiscussionMode] = useState<DiscussionMode>("chaired");
  const [title, setTitle] = useState("");
  const [agenda, setAgenda] = useState("");
  const [participants, setParticipants] = useState<string[]>([]);
  const [locationId, setLocationId] = useState(game.action_catalog.locations[0]?.id ?? "beishan_park");
  const [notified, setNotified] = useState(true);
  const [date, setDate] = useState(nextDate(game.current_date));
  const [scheduleKindValue, setScheduleKindValue] = useState<ScheduleKind>("meeting");
  const [instructions, setInstructions] = useState("");
  const [sourceDocuments, setSourceDocuments] = useState<string[]>([]);

  const toggleParticipant = (id: string) => setParticipants((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]);
  const formTitle = panel === "talk" ? "找人谈话" : panel === "meeting" ? "召开会议" : panel === "field" ? "现场调研" : panel === "schedule" ? "预定日程" : "交办文稿";

  function submit() {
    if (panel === "talk") return onMutate(() => startConversation(game, credentials, actorId));
    if (panel === "field") return onMutate(() => startFieldVisit(game, credentials, locationId, notified));
    if (panel === "meeting") return onMutate(() => startMeeting(game, credentials, { meeting_type: meetingType, discussion_mode: discussionMode, title: title || "专题研究会", agenda: agenda || "听取情况并研究下一步安排", participant_ids: participants.length ? participants : [actorId] }));
    if (panel === "draft") return onMutate(() => requestDraft(game, credentials, { author_id: actorId, title: title || "情况报告", document_type: "report", instructions: instructions || "根据现有材料形成事实清楚、责任边界明确的报告。", source_document_ids: sourceDocuments }));
    const scheduleParticipants = scheduleKindValue === "conversation" || scheduleKindValue === "superior_meeting" ? [scheduleKindValue === "superior_meeting" ? "superior" : actorId] : participants.length ? participants : [actorId];
    return onMutate(() => scheduleEntry(game, credentials, { date, kind: scheduleKindValue, title: title || "预定工作安排", participant_ids: scheduleKindValue === "field_visit" ? [] : scheduleParticipants, location_id: scheduleKindValue === "field_visit" ? locationId : undefined, meeting_type: scheduleKindValue === "meeting" ? meetingType : undefined, discussion_mode: scheduleKindValue === "meeting" ? discussionMode : undefined, notified }));
  }

  return <div className="drawer-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><section className="action-drawer" role="dialog" aria-modal="true" aria-labelledby="drawer-title"><header><div><p className="section-kicker">工作安排</p><h2 id="drawer-title">{formTitle}</h2></div><button onClick={onClose} aria-label="关闭">×</button></header>{panel === "talk" && <><p className="drawer-help">一次谈话只消耗一次行动点，可连续追问。人物只会依据自己的身份、渠道和亲历作答。</p><ActorSelect actors={game.actors} value={actorId} onChange={setActorId} /></>}{panel === "meeting" && <MeetingFields game={game} meetingType={meetingType} mode={discussionMode} title={title} agenda={agenda} participants={participants} onMeetingType={setMeetingType} onMode={setDiscussionMode} onTitle={setTitle} onAgenda={setAgenda} onToggle={toggleParticipant} />}{panel === "field" && <FieldFields game={game} locationId={locationId} notified={notified} onLocation={setLocationId} onNotified={setNotified} />}{panel === "schedule" && <><label className="field-label" htmlFor="schedule-date">执行日期</label><input id="schedule-date" className="text-input" type="date" min={nextDate(game.current_date)} value={date} onChange={(event) => setDate(event.target.value)} /><label className="field-label" htmlFor="schedule-kind">事项类型</label><select id="schedule-kind" className="text-input" value={scheduleKindValue} onChange={(event) => setScheduleKindValue(event.target.value as ScheduleKind)}><option value="meeting">召开会议</option><option value="conversation">找人谈话</option><option value="field_visit">现场调研</option><option value="superior_meeting">与上级面谈</option></select><label className="field-label" htmlFor="schedule-title">日程名称</label><input id="schedule-title" className="text-input" value={title} onChange={(event) => setTitle(event.target.value)} placeholder="例如：研究北山产业整改" />{scheduleKindValue === "meeting" && <MeetingFields compact game={game} meetingType={meetingType} mode={discussionMode} title={title} agenda={agenda} participants={participants} onMeetingType={setMeetingType} onMode={setDiscussionMode} onTitle={setTitle} onAgenda={setAgenda} onToggle={toggleParticipant} />}{scheduleKindValue === "conversation" && <ActorSelect actors={game.actors.filter((actor) => actor.id !== "superior")} value={actorId} onChange={setActorId} />}{scheduleKindValue === "field_visit" && <FieldFields game={game} locationId={locationId} notified={notified} onLocation={setLocationId} onNotified={setNotified} />}</>}{panel === "draft" && <><p className="drawer-help">秘书或相关人员会在日终结算中处理任务，成稿通常于次日呈送。文稿的事实基础来自你选择的源文件。</p><ActorSelect actors={game.actors.filter((actor) => actor.id !== "superior")} value={actorId} onChange={setActorId} /><label className="field-label" htmlFor="draft-title">文稿标题</label><input id="draft-title" className="text-input" value={title} onChange={(event) => setTitle(event.target.value)} placeholder="关于……的情况报告" /><label className="field-label" htmlFor="draft-instructions">起草要求</label><textarea id="draft-instructions" rows={4} value={instructions} onChange={(event) => setInstructions(event.target.value)} placeholder="说明用途、重点、口径和必须核实的事项。" /><div className="source-checks"><span>引用已有文件</span>{game.documents.map((document) => <label key={document.id}><input type="checkbox" checked={sourceDocuments.includes(document.id)} onChange={() => setSourceDocuments((current) => current.includes(document.id) ? current.filter((item) => item !== document.id) : [...current, document.id])} />{document.title}</label>)}</div></>}<footer><button className="ghost-button" onClick={onClose}>取消</button><button className="primary-button" disabled={busy || (panel === "meeting" && participants.length === 0)} onClick={() => void submit()}>{busy ? "正在处理…" : panel === "schedule" || panel === "draft" ? "确认交办" : "立即开始"}</button></footer></section></div>;
}

function MeetingFields({ game, meetingType, mode, title, agenda, participants, onMeetingType, onMode, onTitle, onAgenda, onToggle, compact = false }: { game: Game; meetingType: MeetingType; mode: DiscussionMode; title: string; agenda: string; participants: string[]; onMeetingType: (value: MeetingType) => void; onMode: (value: DiscussionMode) => void; onTitle: (value: string) => void; onAgenda: (value: string) => void; onToggle: (id: string) => void; compact?: boolean }) {
  return <div className={compact ? "compact-fields" : ""}>{!compact && <><label className="field-label" htmlFor="meeting-title">会议名称</label><input id="meeting-title" className="text-input" value={title} onChange={(event) => onTitle(event.target.value)} placeholder="例如：北山产业整改专题会" /></>}<label className="field-label" htmlFor="meeting-type">会议类型</label><select id="meeting-type" className="text-input" value={meetingType} onChange={(event) => onMeetingType(event.target.value as MeetingType)}>{game.action_catalog.meeting_types.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select><p className="field-note">{game.action_catalog.meeting_types.find((item) => item.id === meetingType)?.description}</p><label className="field-label" htmlFor="discussion-mode">讨论方式</label><select id="discussion-mode" className="text-input" value={mode} onChange={(event) => onMode(event.target.value as DiscussionMode)}><option value="chaired">有主持磋商 · 玩家点名</option><option value="free">无主持磋商 · 角色自主抢话</option></select><label className="field-label" htmlFor="meeting-agenda">议题与希望讨论的问题</label><textarea id="meeting-agenda" rows={3} value={agenda} onChange={(event) => onAgenda(event.target.value)} placeholder="说明要研究的问题，不必替执行单位写完整方案。" /><div className="participant-checks"><span>参会人员</span>{game.actors.filter((actor) => actor.id !== "superior").map((actor) => <label key={actor.id}><input type="checkbox" checked={participants.includes(actor.id)} onChange={() => onToggle(actor.id)} /><strong>{actor.name}</strong><small>{actor.title}</small></label>)}</div></div>;
}

function FieldFields({ game, locationId, notified, onLocation, onNotified }: { game: Game; locationId: string; notified: boolean; onLocation: (value: string) => void; onNotified: (value: boolean) => void }) {
  return <><label className="field-label" htmlFor="field-location">调研地点</label><select id="field-location" className="text-input" value={locationId} onChange={(event) => onLocation(event.target.value)}>{game.action_catalog.locations.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select><div className="visit-mode"><button className={notified ? "active" : ""} onClick={() => onNotified(true)}><strong>提前通知</strong><span>便于安排人员和查阅完整台账，也会给现场准备时间。</span></button><button className={!notified ? "active" : ""} onClick={() => onNotified(false)}><strong>四不两直</strong><span>不发通知、不打招呼，信息可能更真实，也可能见不到关键负责人。</span></button></div></>;
}

function ActorSelect({ actors, value, onChange }: { actors: Actor[]; value: string; onChange: (value: string) => void }) {
  const actor = actors.find((item) => item.id === value) ?? actors[0];
  return <><label className="field-label" htmlFor="actor-select">谈话对象</label><select id="actor-select" className="text-input" value={value} onChange={(event) => onChange(event.target.value)}>{actors.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.title}</option>)}</select>{actor && <div className="actor-preview"><strong>{actor.public_position}</strong><p>{actor.known_note}</p><small>{actor.work_style}</small></div>}</>;
}

function DeskHeading({ kicker, title, detail, action }: { kicker: string; title: string; detail: string; action?: ReactNode }) { return <header className="desk-heading"><div><p className="section-kicker">{kicker}</p><h1>{title}</h1><span>{detail}</span></div>{action}</header>; }
function DeskNavButton({ active, label, count, onClick }: { active: boolean; label: string; count: number; onClick: () => void }) { return <button className={`desk-nav-button ${active ? "active" : ""}`} onClick={onClick}><span>{label}</span><b>{count}</b></button>; }
function ActionButton({ label, note, disabled = false, onClick }: { label: string; note: string; disabled?: boolean; onClick: () => void }) { return <button className="action-button" disabled={disabled} onClick={onClick}><span>{label}</span><small>{note}</small></button>; }
function CenteredMessage({ title, message, loading = false }: { title: string; message: string; loading?: boolean }) { return <main className="centered-message"><div className={loading ? "loading-mark" : "mini-seal"}>{loading ? "" : "岚"}</div><h1>{title}</h1><p>{message}</p></main>; }

function persistCredentials(credentials: Credentials) {
  if (credentials.remember) {
    localStorage.setItem(STORAGE.localKey, credentials.apiKey);
    sessionStorage.removeItem(STORAGE.sessionKey);
  } else {
    sessionStorage.setItem(STORAGE.sessionKey, credentials.apiKey);
    localStorage.removeItem(STORAGE.localKey);
  }
  localStorage.setItem(STORAGE.model, credentials.model);
  localStorage.setItem(STORAGE.apiBase, credentials.apiBase);
}

function errorText(caught: unknown, fallback: string) { return caught instanceof Error ? caught.message : fallback; }
function formatDate(value: string) { return new Intl.DateTimeFormat("zh-CN", { month: "long", day: "numeric", weekday: "short" }).format(new Date(`${value}T00:00:00`)); }
function nextDate(value: string) { const date = new Date(`${value}T00:00:00`); date.setDate(date.getDate() + 1); return date.toISOString().slice(0, 10); }
function briefCategory(value: string) { return ({ news: "昨日动态", report: "报告", request: "请示", superior: "上级事项", schedule: "日程", reminder: "提醒", rumor: "未经核实" } as Record<string, string>)[value] ?? value; }
function pressureLabel(value: string) { return ({ low: "低", medium: "中", high: "高", critical: "紧急" } as Record<string, string>)[value] ?? value; }
function documentStatus(value: string) { return ({ draft: "草稿", in_review: "审核中", ready: "可报送", submitted: "已报送", received: "待阅", returned: "已退回", approved: "已同意", issued: "已印发", archived: "归档" } as Record<string, string>)[value] ?? value; }
function calendarStatus(value: string) { return ({ scheduled: "已预定", tentative: "暂定", due: "今日待办", active: "进行中", completed: "已完成", canceled: "已取消", conflict: "有冲突" } as Record<string, string>)[value] ?? value; }
function scheduleKind(value: string) { return ({ conversation: "谈话", meeting: "会议", superior_meeting: "上级面谈", field_visit: "调研" } as Record<string, string>)[value] ?? value; }
function sceneKind(value: string) { return ({ conversation: "个别谈话", meeting: "会议", superior_meeting: "向上汇报", field_visit: "现场调研" } as Record<string, string>)[value] ?? value; }
