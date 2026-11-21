from app.ai import make_copies

def test_offline_fallback_makes_nine_distinct_copies(monkeypatch):
    monkeypatch.delenv('GEMINI_API_KEY',raising=False)
    monkeypatch.delenv('OLLAMA_URL',raising=False)
    result=make_copies({'quote':'Why does consistent editing improve the educational quality of videos?'},[])
    assert len(result)==9
    assert {(p,a) for p,a,text,provider in result}=={(p,a) for p in ['instagram','youtube','linkedin'] for a in ['Teach It','Tell It','Challenge It']}
    assert all(provider=='template' for p,a,text,provider in result)
