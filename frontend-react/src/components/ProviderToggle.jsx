// ProviderToggle — Local (Ollama) vs Cloud BYOK provider switch. Same contract:
// loadOverride() + onOverrideChange(override|null).
import React, { useEffect, useState } from 'react';
import axios from 'axios';

const API_BASE_URL = 'http://localhost:8000';
const LS_KEY = 'kb-provider-override';

export const loadOverride = () => {
    try {
        return JSON.parse(localStorage.getItem(LS_KEY) || 'null');
    } catch {
        return null;
    }
};

const EnginePanel = ({ onOverrideChange }) => {
    const [catalog, setCatalog] = useState([]);
    const [active, setActive] = useState(null);
    const [mode, setMode] = useState('local');
    const [provider, setProvider] = useState('openai');
    const [model, setModel] = useState('');
    const [apiKey, setApiKey] = useState('');
    const [baseUrl, setBaseUrl] = useState('');
    const [usePerChatOnly, setUsePerChatOnly] = useState(true);
    const [status, setStatus] = useState('');
    const [testing, setTesting] = useState(false);
    const [saving, setSaving] = useState(false);

    useEffect(() => {
        fetchCatalog();
        const saved = loadOverride();
        if (saved) {
            setMode(saved.mode || 'local');
            setProvider(saved.provider || 'openai');
            setModel(saved.model || '');
            setApiKey(saved.apiKey || '');
            setBaseUrl(saved.base_url || '');
            setUsePerChatOnly(saved.usePerChatOnly !== false);
            onOverrideChange && onOverrideChange(saved);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const fetchCatalog = async () => {
        try {
            const res = await axios.get(`${API_BASE_URL}/api/providers`);
            setCatalog(res.data.providers || []);
            setActive(res.data.active || null);
            const lp = res.data.active?.llm_provider;
            if (lp && lp !== 'ollama' && !loadOverride()) {
                setMode('byok');
                setProvider(lp);
                setModel(res.data.active?.llm_model || '');
            }
        } catch (e) {
            console.error('Failed to load providers', e);
        }
    };

    const persistOverride = (patch) => {
        const next = { mode, provider, model, apiKey, base_url: baseUrl, usePerChatOnly, ...patch };
        try {
            if (next.mode === 'local') localStorage.removeItem(LS_KEY);
            else localStorage.setItem(LS_KEY, JSON.stringify(next));
        } catch { /* ignore */ }
        onOverrideChange && onOverrideChange(next.mode === 'local' ? null : next);
    };

    const selected = catalog.find((p) => p.id === provider);

    const handleTest = async () => {
        if (!model) { setStatus('Enter a model name first.'); return; }
        if (selected?.needs_key && !apiKey) { setStatus('Enter your API key first.'); return; }
        setTesting(true);
        setStatus('Testing connection…');
        try {
            const res = await axios.post(`${API_BASE_URL}/api/provider/test`, {
                provider, model, api_key: apiKey, base_url: baseUrl || undefined,
            });
            setStatus(`Connected — reply: "${res.data.sample}"`);
        } catch (e) {
            setStatus(`Connection failed: ${e.response?.data?.detail || e.message}`);
        } finally {
            setTesting(false);
        }
    };

    const handleSave = async () => {
        setSaving(true);
        setStatus('Switching provider…');
        try {
            if (mode === 'local') {
                await axios.put(`${API_BASE_URL}/api/provider`, {
                    llm_provider: 'ollama', llm_model: model || 'llama3',
                });
                try { localStorage.removeItem(LS_KEY); } catch { /* ignore */ }
                onOverrideChange && onOverrideChange(null);
                setStatus('Using local Ollama model.');
            } else if (usePerChatOnly) {
                persistOverride({});
                setStatus('API key is sent with each chat request only — never stored on the server.');
            } else {
                await axios.put(`${API_BASE_URL}/api/provider`, {
                    llm_provider: provider, llm_model: model || undefined,
                    llm_api_key: apiKey, llm_base_url: baseUrl || undefined,
                });
                persistOverride({});
                setStatus('Cloud provider saved as default.');
            }
            fetchCatalog();
        } catch (e) {
            setStatus(`Switch failed: ${e.response?.data?.detail || e.message}`);
        } finally {
            setSaving(false);
        }
    };

    const inputCls = 'mt-1 w-full border border-line bg-paper px-3 py-2 font-mono text-[12.5px] text-ink placeholder:text-faint';

    return (
        <section className="border border-line bg-vellum shadow-card">
            <div className="flex items-baseline justify-between border-b border-line px-4 pb-3 pt-4">
                <h2 className="eyebrow text-smoke">AI Provider</h2>
                {active && (
                    <span className="font-mono text-[11px] text-faint">
                        {active.llm_provider} / {active.llm_model}{active.has_llm_key ? ' · key saved' : ''}
                    </span>
                )}
            </div>

            <div className="p-4">
                <div className="grid grid-cols-2 border border-ink font-mono text-[12px] font-semibold">
                    {[
                        { id: 'local', label: 'I. Local (Ollama)' },
                        { id: 'byok', label: 'II. Cloud (BYOK)' },
                    ].map((t) => (
                        <button
                            key={t.id}
                            onClick={() => { setMode(t.id); persistOverride({ mode: t.id }); }}
                            className={`px-3 py-2 transition-colors ${mode === t.id ? 'bg-ink text-paper' : 'bg-paper text-smoke hover:text-ink'}`}
                        >
                            {t.label}
                        </button>
                    ))}
                </div>

                {mode === 'local' && (
                    <div className="mt-3 flex gap-2">
                        <input value={model} onChange={(e) => setModel(e.target.value)} placeholder="llama3"
                            className={`${inputCls} flex-1`} />
                        <button onClick={handleSave} disabled={saving}
                            className="shrink-0 bg-vermilion px-4 py-2 font-mono text-[12px] font-semibold text-paper hover:bg-ember disabled:opacity-50">
                            {saving ? '…' : 'Run'}
                        </button>
                    </div>
                )}

                {mode === 'byok' && (
                    <div className="mt-3 space-y-3">
                        <div className="grid grid-cols-2 gap-2">
                            <label className="block">
                                <span className="eyebrow text-[10px] text-faint">Provider</span>
                                <select value={provider} onChange={(e) => {
                                    setProvider(e.target.value);
                                    const c = catalog.find((p) => p.id === e.target.value);
                                    setModel(c?.default_model || '');
                                    persistOverride({ provider: e.target.value, model: c?.default_model || '' });
                                }} className={inputCls}>
                                    {catalog.filter((p) => p.id !== 'ollama').map((p) => (
                                        <option key={p.id} value={p.id}>{p.label}</option>
                                    ))}
                                </select>
                            </label>
                            <label className="block">
                                <span className="eyebrow text-[10px] text-faint">Model</span>
                                <input value={model} onChange={(e) => { setModel(e.target.value); persistOverride({ model: e.target.value }); }}
                                    placeholder={selected?.default_model || 'gpt-4o-mini'} className={inputCls} />
                            </label>
                        </div>
                        <label className="block">
                            <span className="eyebrow text-[10px] text-faint">API Key</span>
                            <input type="password" value={apiKey} onChange={(e) => { setApiKey(e.target.value); persistOverride({ apiKey: e.target.value }); }}
                                placeholder="Paste key — sent per request" className={inputCls} />
                        </label>
                        {(provider === 'openai_compatible' || baseUrl) && (
                            <label className="block">
                                <span className="eyebrow text-[10px] text-faint">Base URL</span>
                                <input value={baseUrl} onChange={(e) => { setBaseUrl(e.target.value); persistOverride({ base_url: e.target.value }); }}
                                    placeholder="https://…/v1" className={inputCls} />
                            </label>
                        )}
                        <label className="flex cursor-pointer items-start gap-2 font-mono text-[11.5px] leading-snug text-smoke">
                            <input type="checkbox" checked={usePerChatOnly}
                                onChange={(e) => { setUsePerChatOnly(e.target.checked); persistOverride({ usePerChatOnly: e.target.checked }); }}
                                className="mt-0.5 accent-[#D5431F]" />
                            Send key with each request only (never stored on server)
                        </label>
                        <div className="flex gap-2">
                            <button onClick={handleTest} disabled={testing}
                                className="flex-1 border border-ink bg-paper px-3 py-2 font-mono text-[12px] font-semibold text-ink hover:bg-parchment disabled:opacity-50">
                                {testing ? 'Testing…' : 'Test connection'}
                            </button>
                            <button onClick={handleSave} disabled={saving}
                                className="flex-1 bg-ink px-3 py-2 font-mono text-[12px] font-semibold text-paper hover:bg-soot disabled:opacity-50">
                                {saving ? '…' : usePerChatOnly ? 'Use key' : 'Save key'}
                            </button>
                        </div>
                    </div>
                )}

                {status && (
                    <p className="mt-3 border-l-2 border-butter bg-parchment/60 px-3 py-2 font-mono text-[11.5px] leading-snug text-soot">
                        {status}
                    </p>
                )}
            </div>
        </section>
    );
};

export default EnginePanel;
