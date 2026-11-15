from app.agents import choose_agent, local_reply

def test_routes_study_plan(): assert choose_agent('make a study timetable')=='Study Planner'
def test_routes_documents(): assert choose_agent('search my uploaded PDF')=='Document Researcher'
def test_routes_academic(): assert choose_agent('explain normalization in DBMS')=='Academic Advisor'
def test_local_planner():
    agent,answer=local_reply('create a study plan',[])
    assert agent=='Study Planner' and 'break' in answer.lower()
def test_docs_no_match():
    agent,answer=local_reply('find this in my uploaded PDF',[])
    assert agent=='Document Researcher' and 'could not find' in answer.lower()
