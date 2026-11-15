import os, re
from typing import Any

AGENTS = {
 'Coordinator': 'You are the coordinator. Understand the student request and delegate to the most relevant specialist. Be transparent about uncertainty.',
 'Academic Advisor': 'Help with course concepts, academic policies, exam preparation and study explanations. Never invent official university policy.',
 'Study Planner': 'Create realistic, time-blocked study plans. Ask for missing constraints only when essential. Include breaks and measurable goals.',
 'Document Researcher': 'Answer only from supplied document excerpts when they are relevant. Cite filenames. If the documents do not contain the answer, say so.',
 'Student Support': 'Help with general campus/student support questions. Do not claim to perform official actions or access private university systems.'
}

def choose_agent(q: str) -> str:
    s=q.lower()
    if any(k in s for k in ['plan','schedule','timetable','study routine','revision']): return 'Study Planner'
    if any(k in s for k in ['pdf','document','uploaded','policy','handbook','notice','circular']): return 'Document Researcher'
    if any(k in s for k in ['course','subject','exam','assignment','concept','explain','syllabus','cgpa']): return 'Academic Advisor'
    if any(k in s for k in ['hostel','library','campus','support','scholarship','fee','transport']): return 'Student Support'
    return 'Coordinator'

def local_reply(question: str, docs: list[dict[str,str]]) -> tuple[str,str]:
    agent=choose_agent(question)
    if agent=='Study Planner':
        return agent, ('Here is a practical starter plan:\n\n1. **10 min** — define one clear outcome.\n2. **40 min** — learn the topic using notes or a lecture.\n3. **10 min** — take a short break.\n4. **40 min** — solve questions or build something.\n5. **15 min** — review mistakes and write a short summary.\n\nTell me your subjects, available hours and deadline, and I can tailor this plan.')
    if agent=='Document Researcher':
        terms=set(re.findall(r'[a-zA-Z0-9]{3,}',question.lower()))
        scored=[]
        for d in docs:
            words=set(re.findall(r'[a-zA-Z0-9]{3,}',d['content'].lower()))
            score=len(terms & words)
            if score: scored.append((score,d))
        scored.sort(key=lambda x:x[0],reverse=True)
        if not scored: return agent, 'I could not find a relevant passage in your uploaded documents. Upload the relevant handbook, notice or PDF, then ask again.'
        out=['I found these relevant passages in your uploaded files:']
        for _,d in scored[:3]:
            excerpt=d['content'][:1100].strip()
            out.append(f"\n**{d['filename']}**\n{excerpt}")
        out.append('\nThis is a keyword-based local retrieval result. Verify important dates and policies against the original document.')
        return agent,'\n'.join(out)
    if agent=='Academic Advisor':
        return agent, 'I can help explain the concept, prepare practice questions or break your syllabus into smaller topics. Share the exact subject/topic or paste the question. I will distinguish general academic guidance from official university rules.'
    if agent=='Student Support':
        return agent, 'I can help you understand common student-support processes and prepare the questions or documents you may need. For official fees, deadlines, hostel rules or campus services, confirm details with your university portal or student office.'
    return agent, 'I am UniAssist, your student-support assistant. I can help with academic explanations, study plans, uploaded documents and general student-support questions. Tell me what you are trying to achieve, and I will guide you step by step.'

async def ai_reply(question: str, history: list[dict[str,str]], docs: list[dict[str,str]]) -> tuple[str,str,str]:
    """OpenAI-compatible live LLM mode. Gracefully falls back if credentials/dependency are absent."""
    mode=os.getenv('AI_MODE','auto').lower()
    endpoint=os.getenv('AZURE_OPENAI_ENDPOINT') or os.getenv('OPENAI_BASE_URL')
    key=os.getenv('AZURE_OPENAI_API_KEY') or os.getenv('OPENAI_API_KEY')
    model=os.getenv('AZURE_OPENAI_DEPLOYMENT') or os.getenv('OPENAI_MODEL')
    if mode=='local' or not (endpoint and key and model):
        a,r=local_reply(question,docs); return a,r,'local'
    try:
        from openai import AsyncOpenAI
        client=AsyncOpenAI(api_key=key,base_url=endpoint.rstrip('/')+'/openai/v1' if 'azure' in endpoint.lower() and not endpoint.rstrip('/').endswith('/openai/v1') else endpoint)
        agent=choose_agent(question)
        excerpts='\n\n'.join(f"[{d['filename']}] {d['content'][:3500]}" for d in docs[:5])
        system=AGENTS.get(agent,AGENTS['Coordinator']) + '\nYou are UniAssist AI. Be helpful, concise and student-friendly. Do not fabricate official university facts. If source material is missing, say what is unknown. Uploaded document excerpts:\n'+(excerpts or 'No uploaded documents.')
        msgs=[{'role':'system','content':system}]
        msgs += history[-8:]
        msgs.append({'role':'user','content':question})
        result=await client.chat.completions.create(model=model,messages=msgs,temperature=0.35,max_tokens=900)
        answer=result.choices[0].message.content or 'I could not generate a response.'
        return agent,answer,'live'
    except Exception as e:
        a,r=local_reply(question,docs)
        return a, r+f'\n\n[Live AI connection unavailable; local fallback is active. Check endpoint, deployment and credentials.]','fallback'
