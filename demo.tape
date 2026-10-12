# CodePulse demo recording.
#
# Renders docs/demo.gif. Install VHS (https://github.com/charmbracelet/vhs),
# then from a checkout of a repo WITH REAL HISTORY run:
#
#     vhs demo.tape
#
# (Run it inside a mature repo so hotspots/reviewers have data to show.)

Output docs/demo.gif

Set FontSize 16
Set Width 1120
Set Height 660
Set Padding 20
Set Theme "Dracula"

Type "# 1. An A–F health badge for your README" Enter
Type "codepulse . --badge" Sleep 500ms Enter
Sleep 3s

Type "# 2. Score what a pull request changes" Enter
Type "codepulse . --changed HEAD~20" Sleep 500ms Enter
Sleep 4s

Type "# 3. Who knows this file best?" Enter
Type "codepulse . --who src/codepulse/cli.py" Sleep 500ms Enter
Sleep 4s
