# Creates original, clearly labeled synthetic narration for a reproducible local demo.
$ErrorActionPreference='Stop'
$project=Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $project
$ffmpegBuild=Get-ChildItem -LiteralPath "$project/.tools/ffmpeg" -Directory | Select-Object -First 1
$env:PATH=(Join-Path $ffmpegBuild.FullName 'bin')+[IO.Path]::PathSeparator+$env:PATH
$demoDir=Join-Path $project 'demo'
New-Item -ItemType Directory -Force -Path $demoDir | Out-Null
Add-Type -AssemblyName System.Speech
$speaker=New-Object System.Speech.Synthesis.SpeechSynthesizer
$speaker.Rate=-2
$paragraphs=@(
'Welcome to this original Remixora demonstration. You are listening to a synthetic narrator reading a script about thoughtful content creation. No customer story or campaign result is being claimed. We will explore how one recording can become several useful lessons while preserving its meaning and respecting the people who made it.',
'First, start with a question your audience actually asks. A useful short clip does not need to explain everything. It needs to explain one thing clearly. Choose a question, give a practical answer, and show the reason behind that answer. This is how a small moment becomes a complete lesson.',
'Why does context matter when editing a longer conversation? Because a statement can mean something different when the surrounding explanation disappears. Before selecting a clip, listen to the previous sentence and the next sentence. If the excerpt changes the original meaning, choose a wider range or leave that moment in the source.',
'Here is an important lesson about opening lines. Tell the viewer what they can learn without promising a result you cannot support. A simple opening can invite attention without exaggeration. First identify the question, then explain the idea, and finally give the viewer a thoughtful next step they can choose to try.',
'Imagine a fictional creator recording a conversation at a kitchen table. When I began writing this example, the room was quiet and the camera was simple. The point of the story was not the equipment. It was the moment someone explained an idea so clearly that the conversation suddenly felt useful.',
'In this fictional scene, we were reviewing an old recording together. One day I noticed that the most meaningful sentence had almost been removed. Then I listened to the surrounding conversation again. My experience in the story changed because the quiet explanation mattered more than the loud introduction at the beginning.',
'One common mistake is assuming that every post should sound the same. That idea is wrong when the audience expects different kinds of context. Instead, preserve the central point and adjust the framing. A professional discussion can invite reflection, while a short video can introduce one focused question from the very same source.',
'Another myth is that more dramatic words always make a better opening. Actually, an unsupported claim can weaken trust. However, a specific question can still create curiosity. The mistake is confusing confidence with evidence. Instead, write an opening you can defend by pointing to the exact words in the original recording.',
'How can editing teach a system about your voice? First compare a generated draft with your revision. If you remove every hashtag, that is evidence for a narrow preference. Ask for approval before applying it again. The lesson is to remember the style choice without copying the old caption into an unrelated future topic.',
'A content calendar is a plan, not proof that a post was published. Choose a date, confirm the timezone, and review the final caption before approving the slot. If another post already occupies the same platform and time, adjust the schedule. A clear status helps everyone understand what still needs human attention.',
'Performance feedback needs comparable observations. Do not compare a first-day result with a month of accumulated activity. Group posts by platform and measurement window, count distinct examples, and explain uncertainty. A small sample can suggest a question to investigate. It cannot establish that one editorial angle will always produce a better result.',
'The final lesson is simple. Keep the original source close, make every transformation reviewable, and let the creator decide what to publish. This demonstration uses original scripted narration and local tools. It does not represent a real customer campaign. Your own recordings and your own judgment are what turn the workflow into meaningful creative work.'
)
for($i=0;$i -lt $paragraphs.Count;$i++){
    $speaker.SetOutputToWaveFile((Join-Path $demoDir ("part-{0:D2}.wav" -f $i)))
    $speaker.Speak($paragraphs[$i])
    $speaker.SetOutputToNull()
}
$speaker.Dispose()
$paragraphs | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $demoDir 'narration.json') -Encoding utf8
python scripts/assemble_demo.py
