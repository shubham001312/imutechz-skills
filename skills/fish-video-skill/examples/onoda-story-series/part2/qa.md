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
| duration | PASS | 27.00s (timeline 27.00s) |
| platform length | PASS | 27.0s (max 180s) |
| bitrate | PASS | 12.12 Mb/s, 40.9 MB |
| loudness | PASS | -12.4 LUFS (target -12) |
| true peak | PASS | -1.8 dBTP (max -1.0) |
| dropouts | PASS | 0 silent gaps during narration |
| black frames | PASS | 0 black runs |
| captions | PASS | 14 cues |
| voice | PASS | all lines voiced |
| mix balance | PASS | speech -11.9 dBFS, gaps -19.3 dBFS (voice over bed 7.4 dB); sfx yes |
| speaker translation | PASS | a phone loses 4.2 dB of the mix; mono change -0.0 dB; on a phone: speech -15.9, bed between lines -22.8 dBFS (gap 6.9 dB) |
| explicit cues | PASS | every hand-placed cue was placed |
| bare frame | PASS | no quarter of the frame stays empty |
| text lint | PASS | 0 issues |
| stage errors | PASS | [] |
| facts | PASS | 4 numbers checked |

Contact sheet: `contact.png`
