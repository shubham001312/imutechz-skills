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
| duration | PASS | 28.50s (timeline 28.50s) |
| platform length | PASS | 28.5s (max 180s) |
| bitrate | PASS | 1.49 Mb/s, 5.3 MB |
| loudness | PASS | -14.2 LUFS (target -14) |
| true peak | PASS | -1.9 dBTP (max -1.5) |
| dropouts | PASS | 0 silent gaps during narration |
| black frames | PASS | 0 black runs |
| captions | PASS | 14 cues |
| voice | PASS | all lines voiced |
| mix balance | PASS | speech -13.4 dBFS, gaps -22.0 dBFS (voice over bed 8.7 dB); sfx yes |
| text lint | PASS | 0 issues |
| stage errors | PASS | [] |
| facts | PASS | 4 numbers checked |

Contact sheet: `contact.png`
