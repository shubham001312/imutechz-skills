# QA report

## youtube: PASS

`final.mp4`

| check | status | detail |
|---|---|---|
| codec | PASS | h264 High yuv420p |
| resolution | PASS | 1920x1080 (want 1920x1080) |
| fps | PASS | 30.000 |
| audio | PASS | aac 48000 Hz 2 ch |
| faststart | PASS | moov before mdat |
| duration | PASS | 555.00s (timeline 555.00s) |
| bitrate | PASS | 15.98 Mb/s, 1108.9 MB |
| loudness | PASS | -14.2 LUFS (target -14) |
| true peak | PASS | -1.2 dBTP (max -1.5) |
| dropouts | PASS | 0 silent gaps during narration |
| black frames | PASS | 0 black runs |
| captions | PASS | 216 cues |
| voice | PASS | all lines voiced |
| mix balance | PASS | speech -13.9 dBFS, gaps -20.7 dBFS (voice over bed 6.7 dB); sfx yes |
| speaker translation | PASS | a phone loses 4.1 dB of the mix; mono change -0.0 dB; on a phone: speech -17.9, bed between lines -25.8 dBFS (gap 7.9 dB) |
| explicit cues | PASS | every hand-placed cue was placed |
| bare frame | PASS | no quarter of the frame stays empty |
| text lint | PASS | 0 issues |
| stage errors | PASS | [] |
| facts | PASS | 1 numbers checked |

Contact sheet: `contact.png`
