# QA report

## shorts: PASS

`final.mp4`

| check | status | detail |
|---|---|---|
| codec | PASS | h264 High yuv420p |
| resolution | PASS | 1080x1920 (want 1080x1920) |
| fps | PASS | 30.000 |
| audio | PASS | aac 48000 Hz 2 ch |
| faststart | PASS | moov before mdat |
| duration | PASS | 25.50s (timeline 25.50s) |
| platform length | PASS | 25.5s (max 180s) |
| bitrate | PASS | 12.20 Mb/s, 38.9 MB |
| loudness | PASS | -12.6 LUFS (target -12) |
| true peak | PASS | -2.0 dBTP (max -1.0) |
| dropouts | PASS | 0 silent gaps during narration |
| black frames | PASS | 0 black runs |
| captions | PASS | 15 cues |
| voice | PASS | all lines voiced |
| mix balance | PASS | speech -12.5 dBFS, gaps -16.7 dBFS (voice over bed 4.2 dB); sfx yes |
| speaker translation | PASS | a phone loses 4.2 dB of the mix; mono change -0.0 dB; on a phone: speech -16.3, bed between lines -23.5 dBFS (gap 7.2 dB) |
| explicit cues | PASS | every hand-placed cue was placed |
| bare frame | PASS | no quarter of the frame stays empty |
| text lint | PASS | 0 issues |
| stage errors | PASS | [] |
| facts | PASS | 4 numbers checked |

Contact sheet: `contact.png`
