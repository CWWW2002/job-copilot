import { useState } from 'react'

const MARKET_STYLE_OPTIONS = [
  { value: 'us', label: '北美市场' },
  { value: 'china', label: '国内市场' },
]

function ScoreGauge({ score }) {
  const color =
    score >= 75 ? 'text-emerald-600' : score >= 50 ? 'text-amber-600' : 'text-red-600'
  return (
    <div className="flex flex-col items-center">
      <div className={`text-6xl font-bold ${color}`}>{score}</div>
      <div className="text-sm text-gray-500 mt-1">匹配分数 / 100</div>
    </div>
  )
}

const TYPE_STYLES = {
  数字来源: 'bg-blue-100 text-blue-700',
  '个人贡献 vs 团队贡献': 'bg-purple-100 text-purple-700',
  技术选型: 'bg-amber-100 text-amber-700',
  时间线合理性: 'bg-rose-100 text-rose-700',
  JD关联: 'bg-teal-100 text-teal-700',
  其他: 'bg-gray-100 text-gray-700',
}

function StressTestGroup({ group, groupIdx, expanded, onToggle, answers, onAnswerChange }) {
  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden">
      <button
        onClick={() => onToggle(groupIdx)}
        className="w-full flex items-center justify-between px-4 py-3 bg-gray-50 hover:bg-gray-100 text-left"
      >
        <span className="font-medium text-gray-800">{group.experience_title}</span>
        <span className="text-gray-400 text-sm">
          {group.questions.length} 条追问 {expanded ? '▲' : '▼'}
        </span>
      </button>
      {expanded && (
        <div className="p-4 space-y-4">
          {group.questions.map((q, qIdx) => (
            <div key={qIdx} className="border border-gray-100 rounded-lg p-3 space-y-2">
              <div className="flex items-center gap-2">
                <span
                  className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                    TYPE_STYLES[q.type] || TYPE_STYLES['其他']
                  }`}
                >
                  {q.type}
                </span>
              </div>
              <p className="text-sm font-medium text-gray-900">{q.question}</p>
              <p className="text-xs text-gray-500">为什么会被这样追问:{q.why_asked}</p>
              <div className="bg-amber-50 border border-amber-100 rounded-md p-2">
                <p className="text-xs text-amber-800">
                  <span className="font-semibold">答题思路提示:</span> {q.answer_guidance}
                </p>
              </div>
              <textarea
                value={answers[`${groupIdx}-${qIdx}`] || ''}
                onChange={(e) => onAnswerChange(groupIdx, qIdx, e.target.value)}
                rows={3}
                placeholder="在这里练习你的回答(不会保存,刷新页面即清空)..."
                className="w-full border border-gray-300 rounded-md p-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
              />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function StepCard({ step, title, done, children }) {
  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
      <div className="flex items-center gap-3 mb-4">
        <div
          className={`w-7 h-7 shrink-0 rounded-full flex items-center justify-center text-sm font-semibold ${
            done ? 'bg-emerald-500 text-white' : 'bg-gray-200 text-gray-600'
          }`}
        >
          {done ? '✓' : step}
        </div>
        <h2 className="text-lg font-semibold text-gray-800">{title}</h2>
      </div>
      {children}
    </div>
  )
}

export default function App() {
  const [resume, setResume] = useState(null)
  const [resumeError, setResumeError] = useState('')
  const [resumeLoading, setResumeLoading] = useState(false)

  const [jdText, setJdText] = useState('')
  const [jd, setJd] = useState(null)
  const [jdError, setJdError] = useState('')
  const [jdLoading, setJdLoading] = useState(false)
  const [marketStyle, setMarketStyle] = useState('us')

  const [report, setReport] = useState(null)
  const [matchError, setMatchError] = useState('')
  const [matchLoading, setMatchLoading] = useState(false)

  const [tailored, setTailored] = useState(null)
  const [tailorError, setTailorError] = useState('')
  const [tailorLoading, setTailorLoading] = useState(false)
  const [copied, setCopied] = useState(false)

  const [stressTestSource, setStressTestSource] = useState('original')
  const [stressTest, setStressTest] = useState(null)
  const [stressTestError, setStressTestError] = useState('')
  const [stressTestLoading, setStressTestLoading] = useState(false)
  const [expandedGroups, setExpandedGroups] = useState({})
  const [practiceAnswers, setPracticeAnswers] = useState({})

  async function handleResumeUpload(e) {
    const file = e.target.files?.[0]
    if (!file) return
    setResumeError('')
    setResumeLoading(true)
    setResume(null)
    setReport(null)
    setTailored(null)
    try {
      const formData = new FormData()
      formData.append('file', file)
      const res = await fetch('/api/resume/upload', { method: 'POST', body: formData })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || '上传失败')
      setResume(data)
    } catch (err) {
      setResumeError(err.message)
    } finally {
      setResumeLoading(false)
    }
  }

  async function handleJdSubmit() {
    setJdError('')
    setJdLoading(true)
    setJd(null)
    setReport(null)
    setTailored(null)
    try {
      const res = await fetch('/api/jd', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ raw_text: jdText }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'JD提交失败')
      setJd(data)
      setMarketStyle(data.suggested_market_style === 'china' ? 'china' : 'us')
    } catch (err) {
      setJdError(err.message)
    } finally {
      setJdLoading(false)
    }
  }

  async function handleGenerateReport() {
    if (!resume || !jd) return
    setMatchError('')
    setMatchLoading(true)
    setReport(null)
    try {
      const res = await fetch('/api/match', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ resume_id: resume.id, jd_id: jd.id, market_style: marketStyle }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || '生成报告失败')
      setReport(data)
    } catch (err) {
      setMatchError(err.message)
    } finally {
      setMatchLoading(false)
    }
  }

  async function handleGenerateTailored() {
    if (!resume || !jd) return
    setTailorError('')
    setTailorLoading(true)
    setTailored(null)
    setCopied(false)
    try {
      const res = await fetch('/api/tailor', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ resume_id: resume.id, jd_id: jd.id, market_style: marketStyle }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || '生成定制简历失败')
      setTailored(data)
    } catch (err) {
      setTailorError(err.message)
    } finally {
      setTailorLoading(false)
    }
  }

  async function handleGenerateStressTest() {
    if (!resume) return
    if (stressTestSource === 'tailored' && !tailored) return
    setStressTestError('')
    setStressTestLoading(true)
    setStressTest(null)
    setExpandedGroups({})
    setPracticeAnswers({})
    try {
      const body =
        stressTestSource === 'tailored'
          ? { resume_source: 'tailored', tailored_resume_id: tailored.id }
          : { resume_source: 'original', resume_id: resume.id }
      const res = await fetch('/api/resume/stress-test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || '生成压力测试失败')
      setStressTest(data)
      setExpandedGroups({ 0: true })
    } catch (err) {
      setStressTestError(err.message)
    } finally {
      setStressTestLoading(false)
    }
  }

  function toggleGroup(groupIdx) {
    setExpandedGroups((prev) => ({ ...prev, [groupIdx]: !prev[groupIdx] }))
  }

  function handleAnswerChange(groupIdx, qIdx, value) {
    setPracticeAnswers((prev) => ({ ...prev, [`${groupIdx}-${qIdx}`]: value }))
  }

  async function handleCopy() {
    if (!tailored) return
    try {
      await navigator.clipboard.writeText(tailored.content)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      setTailorError('复制失败,请手动选中文本复制')
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 py-10 px-4">
      <div className="max-w-3xl mx-auto space-y-6">
        <header className="text-center mb-2">
          <h1 className="text-2xl font-bold text-gray-900">求职简历投递辅助工具</h1>
          <p className="text-gray-500 mt-1 text-sm">
            上传简历 → 粘贴JD → 选择市场风格 → 匹配分析 / 定制简历 / 面试压力测试
          </p>
        </header>

        <StepCard step={1} title="上传简历(PDF / DOCX)" done={!!resume}>
          <input
            type="file"
            accept=".pdf,.docx"
            onChange={handleResumeUpload}
            className="block w-full text-sm text-gray-700 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-indigo-50 file:text-indigo-700 file:font-medium hover:file:bg-indigo-100"
          />
          {resumeLoading && <p className="text-sm text-gray-500 mt-2">解析中...</p>}
          {resumeError && <p className="text-sm text-red-600 mt-2">{resumeError}</p>}
          {resume && (
            <p className="text-sm text-emerald-700 mt-2">
              已解析「{resume.filename}」,共 {resume.char_count} 字
            </p>
          )}
        </StepCard>

        <StepCard step={2} title="粘贴职位描述(JD)并选择市场风格" done={!!jd}>
          <textarea
            value={jdText}
            onChange={(e) => setJdText(e.target.value)}
            rows={6}
            placeholder="粘贴完整的职位描述文本..."
            className="w-full border border-gray-300 rounded-lg p-3 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
          />
          <button
            onClick={handleJdSubmit}
            disabled={jdLoading || jdText.trim().length < 20}
            className="mt-3 px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {jdLoading ? '识别中...' : '提交 JD'}
          </button>
          {jdError && <p className="text-sm text-red-600 mt-2">{jdError}</p>}

          {jd && (
            <div className="mt-4 border-t border-gray-100 pt-4">
              <p className="text-xs text-gray-400 mb-2">
                AI建议:{jd.suggested_market_style === 'china' ? '国内市场' : '北美市场'}(
                {jd.suggestion_method === 'llm' ? 'LLM判断' : '关键词判断'}),可手动切换
              </p>
              <div className="flex gap-2">
                {MARKET_STYLE_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    onClick={() => setMarketStyle(opt.value)}
                    className={`px-4 py-2 rounded-lg text-sm font-medium border transition ${
                      marketStyle === opt.value
                        ? 'bg-indigo-600 text-white border-indigo-600'
                        : 'bg-white text-gray-600 border-gray-300 hover:border-indigo-400'
                    }`}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>
          )}
        </StepCard>

        <StepCard step={3} title="生成匹配报告" done={!!report}>
          <button
            onClick={handleGenerateReport}
            disabled={!resume || !jd || matchLoading}
            className="px-4 py-2 bg-emerald-600 text-white text-sm font-medium rounded-lg hover:bg-emerald-700 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {matchLoading ? '分析中,请稍候...' : '生成匹配报告'}
          </button>
          {(!resume || !jd) && (
            <p className="text-xs text-gray-400 mt-2">请先完成上传简历和提交JD</p>
          )}
          {matchError && <p className="text-sm text-red-600 mt-2">{matchError}</p>}

          {report && (
            <div className="mt-6 space-y-6">
              <ScoreGauge score={report.score} />

              <div>
                <h3 className="font-semibold text-gray-800 mb-2">✅ 匹配的技能点</h3>
                <ul className="space-y-2">
                  {report.matched_skills.map((item, idx) => (
                    <li key={idx} className="bg-emerald-50 border border-emerald-100 rounded-lg p-3">
                      <div className="font-medium text-emerald-800">{item.skill}</div>
                      <div className="text-sm text-gray-600 mt-1">依据:{item.evidence}</div>
                    </li>
                  ))}
                </ul>
              </div>

              <div>
                <h3 className="font-semibold text-gray-800 mb-2">⚠️ 缺失 / 不匹配的技能点</h3>
                <ul className="space-y-2">
                  {report.missing_skills.map((item, idx) => (
                    <li
                      key={idx}
                      className="bg-red-50 border border-red-100 rounded-lg p-3 text-sm text-red-800"
                    >
                      {item}
                    </li>
                  ))}
                </ul>
              </div>

              <div className="bg-indigo-50 border border-indigo-100 rounded-lg p-4 space-y-1">
                <h3 className="font-semibold text-indigo-900 mb-1">💡 建议</h3>
                <p className="text-sm text-indigo-800">{report.summary.zh}</p>
                <p className="text-sm text-indigo-800">{report.summary.en}</p>
              </div>
            </div>
          )}
        </StepCard>

        <StepCard step={4} title="生成定制简历" done={!!tailored}>
          <button
            onClick={handleGenerateTailored}
            disabled={!resume || !jd || tailorLoading}
            className="px-4 py-2 bg-amber-600 text-white text-sm font-medium rounded-lg hover:bg-amber-700 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {tailorLoading ? '生成中,请稍候...' : '生成定制简历'}
          </button>
          {(!resume || !jd) && (
            <p className="text-xs text-gray-400 mt-2">请先完成上传简历和提交JD</p>
          )}
          {tailorError && <p className="text-sm text-red-600 mt-2">{tailorError}</p>}

          {tailored && (
            <div className="mt-6">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs text-gray-400">
                  按{tailored.market_style === 'china' ? '国内市场' : '北美市场'}风格生成
                </span>
                <button
                  onClick={handleCopy}
                  className="px-3 py-1.5 bg-gray-800 text-white text-xs font-medium rounded-lg hover:bg-gray-900"
                >
                  {copied ? '已复制 ✓' : '复制文本'}
                </button>
              </div>
              <pre className="whitespace-pre-wrap break-words bg-gray-50 border border-gray-200 rounded-lg p-4 text-sm text-gray-800 font-mono max-h-[600px] overflow-y-auto">
                {tailored.content}
              </pre>
            </div>
          )}
        </StepCard>

        <StepCard step={5} title="面试压力测试" done={!!stressTest}>
          <div className="flex gap-2 mb-3">
            <button
              onClick={() => setStressTestSource('original')}
              className={`px-4 py-2 rounded-lg text-sm font-medium border transition ${
                stressTestSource === 'original'
                  ? 'bg-indigo-600 text-white border-indigo-600'
                  : 'bg-white text-gray-600 border-gray-300 hover:border-indigo-400'
              }`}
            >
              基于原始简历
            </button>
            <button
              onClick={() => setStressTestSource('tailored')}
              disabled={!tailored}
              className={`px-4 py-2 rounded-lg text-sm font-medium border transition disabled:opacity-40 disabled:cursor-not-allowed ${
                stressTestSource === 'tailored'
                  ? 'bg-indigo-600 text-white border-indigo-600'
                  : 'bg-white text-gray-600 border-gray-300 hover:border-indigo-400'
              }`}
            >
              基于定制简历{!tailored && '(需先完成步骤4)'}
            </button>
          </div>
          <button
            onClick={handleGenerateStressTest}
            disabled={!resume || (stressTestSource === 'tailored' && !tailored) || stressTestLoading}
            className="px-4 py-2 bg-rose-600 text-white text-sm font-medium rounded-lg hover:bg-rose-700 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {stressTestLoading ? '生成中,请稍候...' : '生成压力测试'}
          </button>
          {!resume && <p className="text-xs text-gray-400 mt-2">请先完成上传简历</p>}
          {stressTestError && <p className="text-sm text-red-600 mt-2">{stressTestError}</p>}

          {stressTest && (
            <div className="mt-6 space-y-3">
              {stressTest.groups.map((group, idx) => (
                <StressTestGroup
                  key={idx}
                  group={group}
                  groupIdx={idx}
                  expanded={!!expandedGroups[idx]}
                  onToggle={toggleGroup}
                  answers={practiceAnswers}
                  onAnswerChange={handleAnswerChange}
                />
              ))}
            </div>
          )}
        </StepCard>
      </div>
    </div>
  )
}
