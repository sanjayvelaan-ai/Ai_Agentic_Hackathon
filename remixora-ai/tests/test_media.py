from app.media import parse_subtitles, candidates

def test_srt_timestamps():
    text='''1\n00:00:00,000 --> 00:00:12,000\nHere is the first lesson.\n\n2\n00:00:12,000 --> 00:00:33,000\nWhy is this an important lesson for creators?\n\n3\n00:00:33,000 --> 00:00:50,000\nBecause useful advice should be clear.\n'''
    segments=parse_subtitles(text)
    assert segments[1]['start']==12
    assert segments[1]['end']==33
    picks=candidates(segments,60)
    assert picks and 0<=picks[0]['start']<picks[0]['end']<=60
    assert 'heuristic' == picks[0]['source']

def test_timestamp_required():
    import pytest
    with pytest.raises(ValueError):parse_subtitles('plain text only')
