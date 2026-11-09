from scdp.core import canonical,sha
from scdp.story import project
from scdp.translation import align


def story(texts):
    frames=[{"id":0,"speaker":"Fiction","text":t} for t in texts]
    return project("demo/fiction",frames,sha(canonical(frames)),sha(canonical(frames)))


def source(texts, translations):
    return {"path":"data/story/fiction.csv","sha256":"0"*64,"identity":"synthetic",
            "rows":[{"id":"0","speaker":"Fiction","text":t,"translation":v,"field":"text","line":i+2} for i,(t,v) in enumerate(zip(texts,translations))]}


def test_repeated_occurrences_and_revision():
    original=story(["A","same","B","same","C"])
    src=source(["A","same","B","same","C"],["甲","一","乙","二","丙"])
    assert [r["text"] for r in align(original,[src])]==["甲","一","乙","二","丙"]
    changed=story(["A","revised","B","same","C"])
    assert align(changed,[src])[1]["status"]=="missing"
    ambiguous=story(["same","same","same"])
    assert all(r["status"]=="missing" for r in align(ambiguous,[source(["same"],["一"])]))


def test_translation_only_and_conflicts():
    original=story(["A"])
    assert align(original,[source(["A"],["甲"])])[0]["text"]=="甲"
    assert align(original,[source(["A"],["乙"])])[0]["text"]=="乙"
    assert align(original,[source(["A"],["甲"]),source(["A"],["乙"])])[0]["status"]=="ambiguous"
    assert align(original,[source(["A"],[""])])[0]["status"]=="missing"
