import os, re
from typing import Any
import httpx

AGENTS = {
 'Coordinator': 'You are the coordinator. Understand the student request and delegate to the most relevant specialist. Be transparent about uncertainty.',
 'Academic Advisor': 'Help with course concepts, academic policies, exam preparation and study explanations. Never invent official university policy.',
 'Study Planner': 'Create realistic, time-blocked study plans. Ask for missing constraints only when essential. Include breaks and measurable goals.',
 'Document Researcher': 'Answer only from supplied document excerpts when they are relevant. Cite filenames. If the documents do not contain the answer, say so.',
 'Student Support': 'Help with general campus/student support questions. Do not claim to perform official actions or access private university systems.'
}

def choose_agent(q: str) -> str:
    s = q.lower()
    if any(k in s for k in ['plan', 'schedule', 'timetable', 'study routine', 'revision']): return 'Study Planner'
    if any(k in s for k in ['pdf', 'document', 'uploaded', 'policy', 'handbook', 'notice', 'circular']): return 'Document Researcher'
    if any(k in s for k in ['course', 'subject', 'exam', 'assignment', 'concept', 'explain', 'syllabus', 'cgpa']): return 'Academic Advisor'
    if any(k in s for k in ['hostel', 'library', 'campus', 'support', 'scholarship', 'fee', 'transport']): return 'Student Support'
    return 'Coordinator'

def local_reply(question: str, docs: list[dict[str, str]]) -> tuple[str, str]:
    agent = choose_agent(question)
    if agent == 'Study Planner':
        return agent, ('Here is a practical starter plan:\n\n1. **10 min** — define one clear outcome.\n2. **40 min** — learn the topic using notes or a lecture.\n3. **10 min** — take a short break.\n4. **40 min** — solve questions or build something.\n5. **15 min** — review mistakes and write a short summary.\n\nTell me your subjects, available hours and deadline, and I can tailor this plan.')
    if agent == 'Document Researcher':
        terms = set(re.findall(r'[a-zA-Z0-9]{3,}', question.lower()))
        scored = []
        for d in docs:
            words = set(re.findall(r'[a-zA-Z0-9]{3,}', d['content'].lower()))
            score = len(terms & words)
            if score: scored.append((score, d))
        scored.sort(key=lambda x: x[0], reverse=True)
        if not scored: return agent, 'I could not find a relevant passage in your uploaded documents. Upload the relevant handbook, notice or PDF, then ask again.'
        out = ['I found these relevant passages in your uploaded files:']
        for _, d in scored[:3]:
            excerpt = d['content'][:1100].strip()
            out.append(f"\n**{d['filename']}**\n{excerpt}")
        out.append('\nThis is a keyword-based local retrieval result. Verify important dates and policies against the original document.')
        return agent, '\n'.join(out)
    if agent == 'Academic Advisor':
        return agent, 'I can help explain the concept, prepare practice questions or break your syllabus into smaller topics. Share the exact subject/topic or paste the question. I will distinguish general academic guidance from official university rules.'
    if agent == 'Student Support':
        return agent, 'I can help you understand common student-support processes and prepare the questions or documents you may need. For official fees, deadlines, hostel rules or campus services, confirm details with your university portal or student office.'
    return agent, 'I am UniAssist, your student-support assistant. I can help with academic explanations, study plans, uploaded documents and general student-support questions. Tell me what you are trying to achieve, and I will guide you step by step.'

async def _gemini_reply(api_key: str, model: str, system: str, history: list[dict[str, str]], question: str) -> str:
    # Try preferred model first, then fallbacks if unavailable/deprecated
    fallback_models = [
        model,
        'gemini-3.5-flash-lite',
        'gemini-3.5-flash',
        'gemini-3.1-flash-lite',
        'gemini-3-flash-preview',
    ]
    # Deduplicate while preserving order
    seen = set()
    models_to_try = []
    for m in fallback_models:
        if m not in seen:
            seen.add(m)
            models_to_try.append(m)

    last_error = None
    for m in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={api_key}"
        contents = []
        for msg in history[-8:]:
            role = "user" if msg.get("role") == "user" else "model"
            text = msg.get("content", "")
            if text:
                contents.append({"role": role, "parts": [{"text": text}]})
        contents.append({"role": "user", "parts": [{"text": question}]})
        payload = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": contents,
            "generationConfig": {"temperature": 0.4, "maxOutputTokens": 1000}
        }
        try:
            async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
                resp = await client.post(url, json=payload, headers={"Content-Type": "application/json"})
                if resp.status_code in (404, 503, 429):
                    last_error = f"{m}: {resp.status_code} {resp.text[:80]}"
                    continue  # Try next model
                resp.raise_for_status()
                data = resp.json()
                candidates = data.get("candidates", [])
                if candidates and "content" in candidates[0]:
                    parts = candidates[0]["content"].get("parts", [])
                    if parts:
                        return parts[0].get("text", "I could not generate a response.")
        except Exception as e:
            last_error = str(e)
            continue

    raise Exception(f"All Gemini models failed. Last error: {last_error}")

async def _openai_reply(endpoint: str, key: str, model: str, system: str, history: list[dict[str, str]], question: str) -> str:
    base = endpoint.rstrip('/')
    if 'azure' in base.lower() and not base.endswith('/openai/v1'):
        url = f"{base}/openai/v1/chat/completions"
    elif not base.endswith('/chat/completions'):
        url = f"{base}/chat/completions" if not base.endswith('/v1') else f"{base}/chat/completions"
    else:
        url = base
        
    msgs = [{'role': 'system', 'content': system}]
    msgs += history[-8:]
    msgs.append({'role': 'user', 'content': question})
    
    headers = {
        'Authorization': f'Bearer {key}',
        'Content-Type': 'application/json'
    }
    if 'azure' in base.lower():
        headers['api-key'] = key
        
    payload = {
        'model': model,
        'messages': msgs,
        'temperature': 0.35,
        'max_tokens': 900
    }
    
    async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data['choices'][0]['message']['content'] or 'I could not generate a response.'

async def ai_reply(question: str, history: list[dict[str, str]], docs: list[dict[str, str]]) -> tuple[str, str, str]:
    mode = os.getenv('AI_MODE', 'auto').lower()
    
    gemini_key = os.getenv('GEMINI_API_KEY')
    gemini_model = os.getenv('GEMINI_MODEL', 'gemini-3.5-flash-lite')
    
    endpoint = os.getenv('AZURE_OPENAI_ENDPOINT') or os.getenv('OPENAI_BASE_URL')
    openai_key = os.getenv('AZURE_OPENAI_API_KEY') or os.getenv('OPENAI_API_KEY')
    openai_model = os.getenv('AZURE_OPENAI_DEPLOYMENT') or os.getenv('OPENAI_MODEL')
    
    has_gemini = bool(gemini_key)
    has_openai = bool(endpoint and openai_key and openai_model)
    
    if mode == 'local' or not (has_gemini or has_openai):
        a, r = local_reply(question, docs)
        return a, r, 'local'
        
    agent = choose_agent(question)
    excerpts = '\n\n'.join(f"[{d['filename']}] {d['content'][:3500]}" for d in docs[:5])
    system = (
        AGENTS.get(agent, AGENTS['Coordinator'])
        + '\nYou are UniAssist AI, a helpful, concise and student-friendly university assistant. '
        'Do not fabricate official university facts. If source material is missing, say what is unknown.\n'
        'Uploaded document excerpts:\n' + (excerpts or 'No uploaded documents.')
    )

    try:
        if has_gemini:
            answer = await _gemini_reply(gemini_key, gemini_model, system, history, question)
            return agent, answer, 'live'
        else:
            answer = await _openai_reply(endpoint, openai_key, openai_model, system, history, question)
            return agent, answer, 'live'
    except Exception as e:
        a, r = local_reply(question, docs)
        return a, r + f'\n\n[Live AI connection failed: {str(e)[:120]}. Local fallback was used.]', 'fallback'
