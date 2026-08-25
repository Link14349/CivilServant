import { useEffect, useMemo, useState } from "react";
import {
  createGame,
  getConfig,
  loadGame,
  submitAction,
  submitConversation,
  validateCredentials,
} from "./api";
import type {
  Actor,
  AppConfig,
  Conversation,
  ConversationChannel,
  ConversationIntent,
  Credentials,
  Game,
  GameMode,
  HistoryEntry,
  Metric,
  Report,
  Turn,
} from "./types";

const STORAGE = {
  sessionKey: "civilservant.deepseek.session-key",
  localKey: "civilservant.deepseek.local-key",
  model: "civilservant.deepseek.model",
  apiBase: "civilservant.deepseek.api-base",
  liveGame: "civilservant.game.live",
  templateGame: "civilservant.game.template",
};

export default function App() {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [credentials, setCredentials] = useState<Credentials | null>(null);
  const [bootError, setBootError] = useState("");

  useEffect(() => {
    getConfig().then(setConfig).catch((error: Error) => setBootError(error.message));
  }, []);

  if (bootError) {
    return <CenteredMessage title="无法启动" message={bootError} />;
  }
  if (!config) {
    return <CenteredMessage title="正在整理案头材料" message="正在连接本机后端……" loading />;
  }
  if (!credentials) {
    return <KeyGate config={config} onEnter={setCredentials} />;
  }
  return (
    <Workspace
      credentials={credentials}
      onChangeCredentials={() => setCredentials(null)}
    />
  );
}

function KeyGate({ config, onEnter }: { config: AppConfig; onEnter: (value: Credentials) => void }) {
  const localKey = localStorage.getItem(STORAGE.localKey) ?? "";
  const sessionKey = sessionStorage.getItem(STORAGE.sessionKey) ?? "";
  const [apiKey, setApiKey] = useState(localKey || sessionKey);
  const [apiBase, setApiBase] = useState(
    localStorage.getItem(STORAGE.apiBase) ?? config.default_api_base,
  );
  const [model, setModel] = useState(
    localStorage.getItem(STORAGE.model) ?? config.default_model,
  );
  const [remember, setRemember] = useState(Boolean(localKey));
  const [validating, setValidating] = useState(false);
  const [error, setError] = useState("");

  async function enterLive() {
    setError("");
    if (!apiKey.trim()) {
      setError("请输入 DeepSeek API Key。没有 Key 时可以进入模板调试模式。");
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
      setError(caught instanceof Error ? caught.message : "验证失败，请检查设置。");
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
          你拥有重要权力，但没有无限资源、完整信息和完美执行力。十二周后，省级产业整改复核组将进驻岚州。
        </p>
        <div className="gate-principles">
          <span>有限权力</span>
          <span>授权执行</span>
          <span>延迟后果</span>
        </div>
      </section>

      <section className="key-card" aria-labelledby="key-title">
        <div className="card-kicker">进入工作台</div>
        <h2 id="key-title">连接 DeepSeek</h2>
        <p className="muted">
          Key 只传给本机后端完成模型请求，不写入游戏存档或服务端日志。
        </p>

        <label className="field-label" htmlFor="api-key">DeepSeek API Key</label>
        <input
          id="api-key"
          className="text-input"
          type="password"
          autoComplete="off"
          placeholder="sk-…"
          value={apiKey}
          onChange={(event) => setApiKey(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") void enterLive();
          }}
        />

        <label className="remember-row">
          <input
            type="checkbox"
            checked={remember}
            onChange={(event) => setRemember(event.target.checked)}
          />
          <span>在这台浏览器上记住 Key</span>
        </label>
        <p className="storage-note">
          {remember
            ? "将保存到 localStorage，直到你主动清除。"
            : "仅保存到 sessionStorage，关闭浏览器后清除。"}
        </p>

        <details className="advanced-settings">
          <summary>高级模型设置</summary>
          <label className="field-label" htmlFor="model-name">模型</label>
          <input
            id="model-name"
            className="text-input"
            value={model}
            onChange={(event) => setModel(event.target.value)}
          />
          <label className="field-label" htmlFor="api-base">API Base URL</label>
          <input
            id="api-base"
            className="text-input"
            value={apiBase}
            onChange={(event) => setApiBase(event.target.value)}
          />
        </details>

        {error && <div className="error-banner" role="alert">{error}</div>}

        <button className="primary-button full" onClick={() => void enterLive()} disabled={validating}>
          {validating ? "正在验证模型…" : "验证并进入"}
        </button>
        <button className="text-button full" onClick={enterTemplate} disabled={validating}>
          没有 Key？进入模板调试模式
        </button>
      </section>
    </main>
  );
}

function Workspace({
  credentials,
  onChangeCredentials,
}: {
  credentials: Credentials;
  onChangeCredentials: () => void;
}) {
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
        setRestoreError(`旧存档未能载入：${error.message}`);
      })
      .finally(() => setRestoring(false));
  }, [gameStorageKey]);

  function rememberGame(next: Game) {
    localStorage.setItem(gameStorageKey, next.id);
    setGame(next);
  }

  function newGame() {
    localStorage.removeItem(gameStorageKey);
    setGame(null);
  }

  if (restoring) {
    return <CenteredMessage title="正在调取存档" message="请稍候……" loading />;
  }
  if (!game) {
    return (
      <GameSetup
        credentials={credentials}
        initialError={restoreError}
        onStarted={rememberGame}
        onChangeCredentials={onChangeCredentials}
      />
    );
  }
  return (
    <GameBoard
      game={game}
      credentials={credentials}
      onGameChange={rememberGame}
      onNewGame={newGame}
      onChangeCredentials={onChangeCredentials}
    />
  );
}

function GameSetup({
  credentials,
  initialError,
  onStarted,
  onChangeCredentials,
}: {
  credentials: Credentials;
  initialError: string;
  onStarted: (game: Game) => void;
  onChangeCredentials: () => void;
}) {
  const [playerName, setPlayerName] = useState("林砚");
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState(initialError);

  async function start() {
    setError("");
    if (!playerName.trim()) {
      setError("请填写主角姓名。");
      return;
    }
    setStarting(true);
    try {
      const game = await createGame(
        playerName.trim(),
        credentials.mode,
        credentials.model,
        credentials.apiBase,
      );
      onStarted(game);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "无法创建游戏。");
    } finally {
      setStarting(false);
    }
  }

  return (
    <main className="setup-shell">
      <header className="setup-header">
        <div>
          <p className="eyebrow">纵向切片 · 六回合</p>
          <h1>岚州市产业整改</h1>
        </div>
        <button className="ghost-button" onClick={onChangeCredentials}>模型设置</button>
      </header>
      <section className="setup-grid">
        <article className="paper-card briefing-card">
          <div className="card-kicker">任前简报</div>
          <h2>你到任第三周，倒计时已经开始</h2>
          <p>
            岚州市人口约 380 万，北山县焦化集群贡献全市约 19% 的规模以上工业增加值。两条生产线未达到阶段整改要求，省级复核将在十二周后进行。
          </p>
          <p>
            集中关停会冲击就业与县级财政；政府兜底技改可能形成新的债务责任；继续拖延则会损害上级信用。你首先需要判断该相信谁、授权给谁。
          </p>
          <div className="scenario-facts">
            <div><strong>12 周</strong><span>复核倒计时</span></div>
            <div><strong>9 人</strong><span>关键行动者</span></div>
            <div><strong>6 回合</strong><span>一条完整事件链</span></div>
          </div>
        </article>
        <article className="paper-card identity-card">
          <div className="card-kicker">任命信息</div>
          <label className="field-label" htmlFor="player-name">主角姓名</label>
          <input
            id="player-name"
            className="text-input large"
            value={playerName}
            maxLength={20}
            onChange={(event) => setPlayerName(event.target.value)}
          />
          <dl className="identity-list">
            <div><dt>年龄</dt><dd>43 岁</dd></div>
            <div><dt>职务</dt><dd>岚州市委书记</dd></div>
            <div><dt>履历</dt><dd>省级部门及外市工作经历</dd></div>
            <div><dt>本地基础</dt><dd>较弱，仍在建立信息渠道</dd></div>
            <div><dt>运行模式</dt><dd>{credentials.mode === "live" ? credentials.model : "模板调试"}</dd></div>
          </dl>
          {error && <div className="error-banner" role="alert">{error}</div>}
          <button className="primary-button full" onClick={() => void start()} disabled={starting}>
            {starting ? "正在整理第一份晨报…" : "到任并打开晨报"}
          </button>
        </article>
      </section>
    </main>
  );
}

function GameBoard({
  game,
  credentials,
  onGameChange,
  onNewGame,
  onChangeCredentials,
}: {
  game: Game;
  credentials: Credentials;
  onGameChange: (game: Game) => void;
  onNewGame: () => void;
  onChangeCredentials: () => void;
}) {
  const [selectedOption, setSelectedOption] = useState("");
  const [customText, setCustomText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [activeReport, setActiveReport] = useState<string | null>(null);
  const [conversationActorId, setConversationActorId] = useState<string | null>(null);

  useEffect(() => {
    setSelectedOption("");
    setCustomText("");
    setActiveReport(null);
    setConversationActorId(null);
  }, [game.turn?.number]);

  const relevantActors = useMemo(() => {
    const ids = new Set(game.turn?.actor_ids ?? []);
    return game.actors.filter((actor) => ids.has(actor.id));
  }, [game.actors, game.turn?.actor_ids]);
  const conversationActor = game.actors.find((actor) => actor.id === conversationActorId) ?? null;
  const turnConversations = game.conversations.filter((item) => item.turn === game.turn?.number);

  async function decide() {
    setError("");
    if (!selectedOption && !customText.trim()) {
      setError("请选择一个方向，或在“其他”中写下你的指令。");
      return;
    }
    setSubmitting(true);
    try {
      const action = selectedOption
        ? { option_id: selectedOption }
        : { custom_text: customText.trim() };
      const next = await submitAction(game, credentials, action);
      onGameChange(next);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "本回合未能提交。");
    } finally {
      setSubmitting(false);
    }
  }

  if (game.status === "completed" && game.outcome) {
    return (
      <OutcomeScreen
        game={game}
        onNewGame={onNewGame}
        onChangeCredentials={onChangeCredentials}
      />
    );
  }

  const turn = game.turn!;
  const latest = game.history.at(-1);
  return (
    <div className="workbench-shell">
      <header className="topbar">
        <div className="brand-lockup">
          <div className="mini-seal">岚</div>
          <div>
            <span className="brand-title">领导工作台</span>
            <span className="brand-subtitle">{game.player_name} · {game.role_title}</span>
          </div>
        </div>
        <div className="topbar-meta">
          <span className={`mode-badge ${game.mode}`}>
            {game.mode === "live" ? game.model : "模板调试"}
          </span>
          <span>{turn.date_label}</span>
          <button className="topbar-button" onClick={onChangeCredentials}>模型设置</button>
        </div>
      </header>

      <div className="workbench-grid">
        <aside className="left-rail">
          <ProgressRail current={turn.number} total={turn.total} />
          <div className="rail-section">
            <div className="rail-heading">治理状态</div>
            <div className="metric-list">
              {game.metrics.map((metric) => <MetricRow key={metric.id} metric={metric} />)}
            </div>
          </div>
          {game.commitments.length > 0 && (
            <div className="rail-section commitments">
              <div className="rail-heading">未结承诺</div>
              {game.commitments.map((item) => <p key={item}>{item}</p>)}
            </div>
          )}
          {game.private_records.length > 0 && (
            <div className="rail-section private-records">
              <div className="rail-heading">私下交办与承诺</div>
              {game.private_records.slice(-4).map((record) => {
                const actor = game.actors.find((item) => item.id === record.actor_id);
                return (
                  <article key={record.id}>
                    <strong>{actor?.name ?? "相关人员"} · {record.status}</strong>
                    <p>{record.summary}</p>
                    <small>{record.visibility}</small>
                  </article>
                );
              })}
            </div>
          )}
        </aside>

        <main className="desk-main">
          {latest && <DecisionReceipt entry={latest} actors={game.actors} />}

          <section className="turn-heading">
            <div>
              <p className="eyebrow">第 {turn.number} 回合 · {turn.phase}</p>
              <h1>{turn.title}</h1>
            </div>
            <div className="turn-number" aria-label={`第 ${turn.number} 回合`}>
              <strong>{String(turn.number).padStart(2, "0")}</strong>
              <span>/ {String(turn.total).padStart(2, "0")}</span>
            </div>
          </section>

          <section className="briefing-strip">
            <span>要情</span>
            <p>{turn.briefing}</p>
          </section>

          <EventDossier turn={turn} />

          <section aria-labelledby="reports-title">
            <div className="section-title-row">
              <div>
                <p className="section-kicker">呈阅材料</p>
                <h2 id="reports-title">案头的报告不会自动说出真相</h2>
              </div>
              <span className="count-label">{turn.reports.length} 份</span>
            </div>
            <div className="report-grid">
              {turn.reports.map((report) => (
                <ReportCard
                  key={report.id}
                  report={report}
                  expanded={activeReport === report.id}
                  onToggle={() => setActiveReport(activeReport === report.id ? null : report.id)}
                />
              ))}
            </div>
          </section>

          <ConversationLog conversations={turnConversations} actors={game.actors} />

          <section className="decision-section" aria-labelledby="decision-title">
            <div className="section-title-row">
              <div>
                <p className="section-kicker">领导指令</p>
                <h2 id="decision-title">{turn.question}</h2>
              </div>
            </div>

            <div className="option-list">
              {turn.options.map((option, index) => (
                <label className={`option-card ${selectedOption === option.id ? "selected" : ""}`} key={option.id}>
                  <input
                    type="radio"
                    name="decision"
                    value={option.id}
                    checked={selectedOption === option.id}
                    onChange={() => {
                      setSelectedOption(option.id);
                      setCustomText("");
                    }}
                  />
                  <span className="option-index">{String.fromCharCode(65 + index)}</span>
                  <span className="option-copy">
                    <strong>{option.label}</strong>
                    <span>{option.description}</span>
                    <small>{option.tradeoff}</small>
                    <span className="responsibility-preview">
                      <b>{option.responsibility.lead_label}</b>
                      <i>{option.responsibility.procedure}</i>
                    </span>
                  </span>
                </label>
              ))}
            </div>

            <div className={`custom-decision ${customText ? "active" : ""}`}>
              <div className="custom-label-row">
                <label htmlFor="custom-action">其他 · 自拟指令</label>
                <span>{customText.length} / 2000</span>
              </div>
              <textarea
                id="custom-action"
                rows={5}
                maxLength={2000}
                placeholder={turn.custom_placeholder}
                value={customText}
                onChange={(event) => {
                  setCustomText(event.target.value);
                  if (event.target.value) setSelectedOption("");
                }}
              />
              <p>只需说明目标、红线和授权。具体实施方案将由相关领导和部门提出。</p>
            </div>

            {error && <div className="error-banner" role="alert">{error}</div>}
            <div className="submit-row">
              <div className="submit-note">
                {game.mode === "live"
                  ? "DeepSeek 将理解你的指令并生成即时人物反应；规则内核负责结算。"
                  : "模板模式按固定规则和关键词解析，不会调用模型。"}
              </div>
              <button className="primary-button" onClick={() => void decide()} disabled={submitting}>
                {submitting ? "正在形成批示与反应…" : "提交本回合决定"}
              </button>
            </div>
          </section>

          {game.history.length > 0 && <HistoryTimeline history={game.history} actors={game.actors} />}
        </main>

        <aside className="right-rail">
          <div className="actor-rail-heading">
            <div className="rail-heading">当前相关人物</div>
            <span>{turn.attention_remaining} / 3 会谈时段</span>
          </div>
          <div className="actor-list">
            {relevantActors.map((actor) => (
              <ActorCard
                key={actor.id}
                actor={actor}
                disabled={turn.attention_remaining <= 0}
                onTalk={() => setConversationActorId(actor.id)}
              />
            ))}
          </div>
          <div className="fiction-note">
            <strong>虚构情境</strong>
            <p>人物、地区、企业与数字均为虚构，不对应现实个案。</p>
          </div>
        </aside>
      </div>
      {conversationActor && (
        <ConversationPanel
          actor={conversationActor}
          game={game}
          credentials={credentials}
          onClose={() => setConversationActorId(null)}
          onGameChange={onGameChange}
        />
      )}
    </div>
  );
}

function EventDossier({ turn }: { turn: Turn }) {
  return (
    <section className="event-dossier" aria-labelledby="dossier-title">
      <div className="section-title-row">
        <div>
          <p className="section-kicker">事件卷宗</p>
          <h2 id="dossier-title">先弄清事情是怎么走到今天的</h2>
        </div>
        <span className="dossier-stamp">内部参阅</span>
      </div>
      <div className="dossier-overview">
        {turn.dossier.overview.map((paragraph) => <p key={paragraph}>{paragraph}</p>)}
      </div>
      <div className="stake-grid">
        {turn.dossier.stakes.map((stake) => (
          <article key={stake.label}>
            <span>{stake.label}</span>
            <strong>{stake.value}</strong>
            <p>{stake.detail}</p>
          </article>
        ))}
      </div>
      <div className="dossier-detail-grid">
        <div className="timeline-block">
          <h3>前情时间线</h3>
          {turn.dossier.timeline.map((item) => (
            <div key={`${item.time}-${item.event}`}>
              <time>{item.time}</time>
              <p>{item.event}</p>
            </div>
          ))}
        </div>
        <div className="fact-status-block">
          <div>
            <h3>已经确认</h3>
            <ul>{turn.dossier.established.map((item) => <li key={item}>{item}</li>)}</ul>
          </div>
          <div>
            <h3>仍有争议</h3>
            <ul>{turn.dossier.contested.map((item) => <li key={item}>{item}</li>)}</ul>
          </div>
        </div>
      </div>
      <div className="procedure-note"><strong>程序提示</strong><span>{turn.dossier.procedure}</span></div>
    </section>
  );
}

function ConversationLog({ conversations, actors }: { conversations: Conversation[]; actors: Actor[] }) {
  if (conversations.length === 0) {
    return (
      <section className="conversation-empty">
        <div><strong>还没有与任何人单独谈过</strong><p>从右侧人物卡发起约谈。每次会谈消耗一个时段，人物只会依据自己掌握的信息作答。</p></div>
      </section>
    );
  }
  return (
    <section className="conversation-log" aria-labelledby="conversation-log-title">
      <div className="section-title-row">
        <div><p className="section-kicker">本回合会谈</p><h2 id="conversation-log-title">人的说法也是材料的一部分</h2></div>
        <span className="count-label">{conversations.length} 次</span>
      </div>
      <div className="conversation-log-list">
        {conversations.map((item) => {
          const actor = actors.find((candidate) => candidate.id === item.actor_id);
          return (
            <article key={item.id}>
              <header><strong>{actor?.name ?? "相关人员"}</strong><span>{channelLabel(item.channel)} · {intentLabel(item.intent)}</span></header>
              <p className="player-line">你：{item.player_message}</p>
              <p className="actor-line">{actor?.name}：{item.reply}</p>
              <footer>{item.consequence_note}{item.requires_formal_decision && <b> · 尚待正式程序</b>}</footer>
            </article>
          );
        })}
      </div>
    </section>
  );
}

function ConversationPanel({
  actor,
  game,
  credentials,
  onClose,
  onGameChange,
}: {
  actor: Actor;
  game: Game;
  credentials: Credentials;
  onClose: () => void;
  onGameChange: (game: Game) => void;
}) {
  const [channel, setChannel] = useState<ConversationChannel>("private_meeting");
  const [intent, setIntent] = useState<ConversationIntent>("inquire");
  const [message, setMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const directHistory = game.conversations.filter((item) => item.actor_id === actor.id);

  useEffect(() => {
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);

  async function send() {
    setError("");
    if (!message.trim()) {
      setError("先写下你准备问什么或交办什么。 ");
      return;
    }
    setSubmitting(true);
    try {
      const next = await submitConversation(game, credentials, {
        actor_id: actor.id,
        channel,
        intent,
        message: message.trim(),
      });
      onGameChange(next);
      setMessage("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "这次会谈未能提交。");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="conversation-overlay" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose();
    }}>
      <section className="conversation-panel" role="dialog" aria-modal="true" aria-labelledby="conversation-title">
        <header className="conversation-panel-header">
          <div className="actor-monogram large">{actor.name.slice(-1)}</div>
          <div><p>人物会谈 · 剩余 {game.turn?.attention_remaining ?? 0} 个时段</p><h2 id="conversation-title">{actor.name}</h2><span>{actor.title}</span></div>
          <button type="button" onClick={onClose} aria-label="关闭会谈">×</button>
        </header>
        <div className="conversation-profile">
          <div><strong>公开立场</strong><p>{actor.public_position}</p></div>
          <div><strong>工作风格</strong><p>{actor.work_style}</p></div>
        </div>
        {directHistory.length > 0 && (
          <div className="direct-history">
            {directHistory.slice(-3).map((item) => (
              <article key={item.id}>
                <p className="player-line">你：{item.player_message}</p>
                <p className="actor-line">{actor.name}：{item.reply}</p>
                <small>{item.consequence_note}</small>
              </article>
            ))}
          </div>
        )}
        <div className="conversation-controls">
          <label>谈话方式
            <select value={channel} onChange={(event) => setChannel(event.target.value as ConversationChannel)}>
              <option value="private_meeting">一对一约谈 · 更坦率、留痕较少</option>
              <option value="written_inquiry">书面询问 · 可追溯、口径更谨慎</option>
            </select>
          </label>
          <label>你的意图
            <select value={intent} onChange={(event) => setIntent(event.target.value as ConversationIntent)}>
              <option value="inquire">询问情况</option>
              <option value="sound_out">试探态度</option>
              <option value="private_assignment">私下交办</option>
              <option value="conditional_exchange">提出条件交换</option>
            </select>
          </label>
        </div>
        <label className="conversation-message">你准备怎么说
          <textarea
            autoFocus
            rows={5}
            maxLength={1200}
            value={message}
            placeholder={conversationPlaceholder(intent, actor.name)}
            onChange={(event) => setMessage(event.target.value)}
          />
        </label>
        <p className="conversation-warning">
          {intent === "private_assignment" || intent === "conditional_exchange"
            ? "谈话可以形成非正式交办或私人承诺；重大资金、关停、重组和人事事项仍需正式程序。"
            : "对方可能不知道、误判或有所保留。会谈内容不是自动核实后的事实。"}
        </p>
        {error && <div className="error-banner" role="alert">{error}</div>}
        <div className="conversation-actions">
          <button className="ghost-button" type="button" onClick={onClose}>暂不谈</button>
          <button className="primary-button" type="button" onClick={() => void send()} disabled={submitting || (game.turn?.attention_remaining ?? 0) <= 0}>
            {submitting ? "正在回应…" : "进行这次会谈"}
          </button>
        </div>
      </section>
    </div>
  );
}

function ProgressRail({ current, total }: { current: number; total: number }) {
  const phases = ["摸清底数", "形成方案", "交换条件", "正式决策", "执行纠偏", "省级复核"];
  return (
    <nav className="progress-rail" aria-label="回合进度">
      <div className="rail-heading">十二周进程</div>
      {phases.slice(0, total).map((phase, index) => {
        const number = index + 1;
        const state = number < current ? "done" : number === current ? "current" : "future";
        return (
          <div className={`progress-item ${state}`} key={phase}>
            <span>{number < current ? "✓" : number}</span>
            <p>{phase}</p>
          </div>
        );
      })}
    </nav>
  );
}

function MetricRow({ metric }: { metric: Metric }) {
  const health = metric.higher_is_better ? metric.value : 100 - metric.value;
  const status = health >= 65 ? "稳" : health >= 45 ? "承压" : "风险";
  return (
    <div className="metric-row" title={metric.description}>
      <div className="metric-top"><span>{metric.label}</span><em>{status}</em></div>
      <div className="metric-track"><span style={{ width: `${health}%` }} /></div>
    </div>
  );
}

function ReportCard({
  report,
  expanded,
  onToggle,
}: {
  report: Report;
  expanded: boolean;
  onToggle: () => void;
}) {
  return (
    <article className={`report-card tone-${report.tone} ${expanded ? "expanded" : ""}`}>
      <div className="report-source">{report.source}</div>
      <h3>{report.title}</h3>
      <p>{report.summary}</p>
      {expanded && <div className="report-detail">{report.detail}</div>}
      <button onClick={onToggle}>{expanded ? "收起附件" : "展开细节"}</button>
    </article>
  );
}

function ActorCard({ actor, disabled, onTalk }: { actor: Actor; disabled: boolean; onTalk: () => void }) {
  const relation = relationLabel(actor.relation);
  return (
    <article className="actor-card">
      <div className="actor-monogram" aria-hidden="true">{actor.name.slice(-1)}</div>
      <div className="actor-copy">
        <div className="actor-name-row"><strong>{actor.name}</strong><span>{relation}</span></div>
        <small>{actor.title}</small>
        <p>{actor.public_position}</p>
        <p className="work-style">{actor.work_style}</p>
        <details><summary>已知情况</summary><div>{actor.known_note}</div></details>
        <button className="talk-button" type="button" onClick={onTalk} disabled={disabled}>
          {disabled ? "本回合时段已用完" : "与他单独谈谈"}
        </button>
      </div>
    </article>
  );
}

function DecisionReceipt({ entry, actors }: { entry: HistoryEntry; actors: Actor[] }) {
  const [open, setOpen] = useState(true);
  return (
    <section className={`decision-receipt ${open ? "open" : ""}`}>
      <button className="receipt-header" onClick={() => setOpen(!open)} aria-expanded={open}>
        <span><strong>上一回合已归档</strong> · {entry.choice}</span>
        <span>{open ? "收起" : "查看"}</span>
      </button>
      {open && (
        <div className="receipt-body">
          <p className="directive-quote">{entry.directive_summary}</p>
          <p>{entry.narrative}</p>
          {entry.responsibility && (
            <div className="receipt-responsibility">
              <strong>{entry.responsibility.lead_label}</strong>
              <span>{entry.responsibility.procedure}</span>
              <small>{entry.responsibility.record}</small>
            </div>
          )}
          {entry.npc_reactions.map((reaction) => {
            const actor = actors.find((candidate) => candidate.id === reaction.actor_id);
            return <blockquote key={`${reaction.actor_id}-${reaction.text}`}>{actor?.name ?? "相关人员"}：{reaction.text}</blockquote>;
          })}
          <div className="effect-chips">{entry.effects.map((effect) => <span key={effect}>{effect}</span>)}</div>
        </div>
      )}
    </section>
  );
}

function HistoryTimeline({ history, actors }: { history: HistoryEntry[]; actors: Actor[] }) {
  return (
    <details className="history-timeline">
      <summary>查看已归档的 {history.length} 回合决策</summary>
      <div className="history-entries">
        {[...history].reverse().map((entry) => (
          <article key={entry.turn}>
            <span>第 {entry.turn} 回合</span>
            <h3>{entry.title}</h3>
            <strong>{entry.choice}</strong>
            <p>{entry.directive_summary}</p>
            {entry.responsibility && <small>责任链：{entry.responsibility.lead_label} · {entry.responsibility.procedure}</small>}
            {entry.npc_reactions.map((reaction) => {
              const actor = actors.find((candidate) => candidate.id === reaction.actor_id);
              return <small key={`${entry.turn}-${reaction.actor_id}`}>{actor?.name}：{reaction.text}</small>;
            })}
          </article>
        ))}
      </div>
    </details>
  );
}

function OutcomeScreen({
  game,
  onNewGame,
  onChangeCredentials,
}: {
  game: Game;
  onNewGame: () => void;
  onChangeCredentials: () => void;
}) {
  const outcome = game.outcome!;
  return (
    <main className="outcome-shell">
      <header className="outcome-topbar">
        <div className="brand-lockup">
          <div className="mini-seal">岚</div>
          <div><span className="brand-title">十二周工作评价</span><span className="brand-subtitle">{game.player_name} · 岚州市委书记</span></div>
        </div>
        <button className="ghost-button light" onClick={onChangeCredentials}>模型设置</button>
      </header>
      <section className="outcome-hero">
        <div className="grade-mark">{outcome.grade}</div>
        <div>
          <p className="eyebrow">省级复核后的阶段评价</p>
          <h1>{outcome.title}</h1>
          <p>{outcome.summary}</p>
        </div>
      </section>
      <section className="outcome-grid">
        <article className="outcome-card achievements">
          <div className="card-kicker">已经建立的基础</div>
          <ul>{outcome.achievements.map((item) => <li key={item}>{item}</li>)}</ul>
        </article>
        <article className="outcome-card risks">
          <div className="card-kicker">尚未结清的代价</div>
          <ul>{outcome.risks.map((item) => <li key={item}>{item}</li>)}</ul>
        </article>
      </section>
      <section className="outcome-epilogue">
        <p>{outcome.epilogue}</p>
      </section>
      <section className="outcome-history">
        <h2>六次关键决定</h2>
        {game.history.map((entry) => (
          <article key={entry.turn}>
            <span>{String(entry.turn).padStart(2, "0")}</span>
            <div><strong>{entry.choice}</strong><p>{entry.directive_summary}</p></div>
          </article>
        ))}
      </section>
      <div className="outcome-actions">
        <button className="primary-button" onClick={onNewGame}>以另一种方式重新开始</button>
      </div>
    </main>
  );
}

function CenteredMessage({
  title,
  message,
  loading = false,
}: {
  title: string;
  message: string;
  loading?: boolean;
}) {
  return (
    <main className="centered-message">
      {loading && <div className="loading-mark" />}
      <h1>{title}</h1>
      <p>{message}</p>
    </main>
  );
}

function persistCredentials(credentials: Credentials) {
  sessionStorage.setItem(STORAGE.sessionKey, credentials.apiKey);
  localStorage.setItem(STORAGE.model, credentials.model);
  localStorage.setItem(STORAGE.apiBase, credentials.apiBase);
  if (credentials.remember) {
    localStorage.setItem(STORAGE.localKey, credentials.apiKey);
  } else {
    localStorage.removeItem(STORAGE.localKey);
  }
}

function relationLabel(value: number) {
  if (value >= 66) return "愿意配合";
  if (value >= 53) return "态度积极";
  if (value >= 43) return "仍在观察";
  if (value >= 32) return "有所保留";
  return "关系紧张";
}

function channelLabel(channel: ConversationChannel) {
  return channel === "private_meeting" ? "一对一约谈" : "书面询问";
}

function intentLabel(intent: ConversationIntent) {
  const labels: Record<ConversationIntent, string> = {
    inquire: "询问情况",
    sound_out: "试探态度",
    private_assignment: "私下交办",
    conditional_exchange: "条件交换",
  };
  return labels[intent];
}

function conversationPlaceholder(intent: ConversationIntent, actorName: string) {
  const placeholders: Record<ConversationIntent, string> = {
    inquire: `例如：${actorName}，你掌握的数字和正式材料有什么不一致？`,
    sound_out: `例如：如果由市长牵头做分期方案，你真实的顾虑是什么？`,
    private_assignment: `例如：先不要扩大范围，你去核一下真实名单和前期会议情况，只向我报告。`,
    conditional_exchange: `例如：你先把真实数据报上来，我再推动市级培训资源，但不承诺兜底。`,
  };
  return placeholders[intent];
}
