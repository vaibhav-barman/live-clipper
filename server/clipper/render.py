"""Graph 2 · Finish + render — layout per piece (static framing, punch alternation), hook zoom-out,
captions/stamps/credit as ASS (burned in AND exported alone with alpha for the face guard),
peak-aligned SFX, two-pass loudnorm with encoder headroom. Rules: stream-layouts, shortform-finish,
sfx-design, render-ops."""
import json
import math
from pathlib import Path

from . import db, media, paths

FPS = media.FPS
CW, CH = 1080, 1920
LANE = 160
BOTTOM = 36
FACE_MAX_W, FACE_MAX_H = 1008, 1050
FACE_SCALE_MAX = 2.25
GAME_SCALE_MAX = 1.10
PUNCH = 1.12


def _even(v):
    return int(v) // 2 * 2


def choose_layout(data):
    W, H = data.get("source_size") or [1920, 1080]
    cam = data.get("facecam")
    if cam and cam[3] >= 360 * H / 1080:
        return "split"
    if data.get("full_frame_face"):
        return "full"
    return "gameplay"


def _split_geometry(data, opts):
    W, H = data["source_size"]
    cx, cy, cw, ch = data["facecam"]
    s = min(FACE_SCALE_MAX, FACE_MAX_W / cw)
    wf = _even(min(FACE_MAX_W, cw * s))
    hf = _even(min(FACE_MAX_H, ch * s))
    h_game = CH - hf - LANE - BOTTOM
    # gameplay crop: aspect 1080:h_game, native, scale ≤ 1.1
    gcw = min(W, H * CW / h_game)
    if CW / gcw > GAME_SCALE_MAX:
        gcw = CW / GAME_SCALE_MAX
    gch = min(H, gcw * h_game / CW)
    g_scale = CW / gcw
    card_h = _even(gch * g_scale)
    gx_c, gy_c = opts.get("game_center") or [W / 2, H / 2]
    gx = int(min(max(gx_c - gcw / 2, 0), W - gcw))
    gy = int(min(max(gy_c - gch / 2, 0), H - gch))
    # keep the facecam OUT of the gameplay card when the frame allows it
    if not opts.get("game_center") and gx < cx + cw and gx + gcw > cx and gy < cy + ch and gy + gch > cy:
        if cx + cw / 2 < W / 2 and cx + cw + gcw <= W:          # cam on the left
            gx = int(cx + cw)
        elif cx + cw / 2 >= W / 2 and cx - gcw >= 0:             # cam on the right
            gx = int(cx - gcw)
    return {"wf": wf, "hf": hf, "s_face": s, "h_game": h_game, "game_crop": [_even(gcw), _even(gch), gx, gy],
            "game_card_h": card_h, "game_y": (h_game - card_h) // 2,
            "face_x": (CW - wf) // 2, "face_y": h_game + LANE}


def _face_crop(cam, face, vw, vh):
    """A vw×vh window inside the cam rect: head x pinned, ~11% headroom over the hair."""
    cx, cy, cw, ch = cam
    if face:
        fx, fy, fw, fh = face
        head_cx = fx + fw / 2
        hair_top = fy - 0.3 * fh
    else:
        head_cx, hair_top = cx + cw / 2, cy + ch * 0.15
    x = min(max(head_cx - vw / 2, cx), cx + cw - vw)
    y = min(max(hair_top - 0.11 * vh, cy), cy + ch - vh)
    return int(x), int(y)


def _piece_filter(i, f0, nf, layout, g, data, k):
    """Filter chain for piece i (input [0:v]) → [p{i}] at 1080×1920."""
    W, H = data["source_size"]
    tr = f"[0:v]trim=start_frame={f0}:end_frame={f0 + nf},setpts=PTS-STARTPTS"
    bg = (f"[b{i}]scale=270:480:force_original_aspect_ratio=increase,crop=270:480,"
          f"boxblur=12:3,eq=brightness=-0.22,scale={CW}:{CH}[bg{i}]")
    if layout == "split":
        cam = data["facecam"]
        s = g["s_face"]
        k = min(k, FACE_SCALE_MAX / s) if s * k > FACE_SCALE_MAX else k
        vw, vh = g["wf"] / s / k, g["hf"] / s / k
        fx, fy = _face_crop(cam, data.get("face"), vw, vh)
        gcw, gch, gx, gy = g["game_crop"]
        return (f"{tr},split=3[b{i}][g{i}][f{i}];{bg};"
                f"[g{i}]crop={gcw}:{gch}:{gx}:{gy},scale={CW}:{g['game_card_h']}:flags=lanczos[gc{i}];"
                f"[f{i}]crop={_even(vw)}:{_even(vh)}:{fx}:{fy},scale={g['wf']}:{g['hf']}:flags=lanczos[fc{i}];"
                f"[bg{i}][gc{i}]overlay=0:{g['game_y']}[t{i}];"
                f"[t{i}][fc{i}]overlay={g['face_x']}:{g['face_y']},setsar=1[p{i}]")
    if layout == "full":
        face = data.get("full_frame_face") or data.get("face") or [W // 2 - 100, H // 3, 200, 200]
        chh = H / k
        cww = chh * 9 / 16
        if cww > W:
            cww, chh = W / k, W / k * 16 / 9
        x, y = _face_crop([0, 0, W, H], face, cww, chh)
        return f"{tr},crop={_even(cww)}:{_even(chh)}:{x}:{y},scale={CW}:{CH}:flags=lanczos,setsar=1[p{i}]"
    # gameplay-only
    gcx, gcy = (data.get("opts") or {}).get("game_center") or [W / 2, H / 2]
    vw, vh = W / k, H / k
    x = int(min(max(gcx - vw / 2, 0), W - vw))
    y = int(min(max(gcy - vh / 2, 0), H - vh))
    sc = min(GAME_SCALE_MAX, CW / vw)
    card_w, card_h = _even(vw * sc), _even(vh * sc)
    return (f"{tr},split=2[b{i}][g{i}];{bg};"
            f"[g{i}]crop={_even(vw)}:{_even(vh)}:{x}:{y},scale={card_w}:{card_h}:flags=lanczos[gc{i}];"
            f"[bg{i}][gc{i}]overlay={(CW - card_w) // 2}:{g['card_y']},setsar=1[p{i}]")


def _ass_time(t):
    t = max(0, t)
    h, r = divmod(t, 3600)
    m, s = divmod(r, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _ass(captions, cap_y, total_s, top_stamp, credit, font):
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {CW}
PlayResY: {CH}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{font},78,&H00FFFFFF,&H00FFFFFF,&H00101010,&H00101010,-1,0,0,0,100,100,-1,0,3,16,0,5,40,140,0,1
Style: Stamp,{font},54,&H00FFFFFF,&H00FFFFFF,&H002B26E0,&H002B26E0,-1,0,0,0,100,100,-1,0,3,18,0,5,40,140,0,1
Style: Credit,{font},40,&H00FFFFFF,&H00FFFFFF,&H00101010,&H00101010,-1,0,0,0,100,100,0,0,3,14,0,5,40,140,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []
    pop = r"{\fad(90,0)\fscx90\fscy90\t(0,140,\fscx100\fscy100)}"
    for c in captions:
        s, e = c["from"] / FPS, c["to"] / FPS
        txt = c["text"].replace("{", "(").replace("}", ")")
        ev.append(f"Dialogue: 1,{_ass_time(s)},{_ass_time(e)},Cap,,0,0,0,,{{\\pos({CW // 2 - 50},{cap_y})}}{pop}{txt}")
    if top_stamp:
        ev.append(f"Dialogue: 2,{_ass_time(0.15)},{_ass_time(min(2.6, total_s))},Stamp,,0,0,0,,"
                  f"{{\\pos({CW // 2 - 50},330)}}{pop}{top_stamp.upper()}")
    if credit:
        ev.append(f"Dialogue: 2,{_ass_time(max(0, total_s - 1.6))},{_ass_time(total_s)},Credit,,0,0,0,,"
                  f"{{\\pos({CW // 2 - 50},300)}}{pop}{credit}")
    return head + "\n".join(ev) + "\n"


def _sfx_plan(mix_lufs, total_s, opts):
    cat_f = paths.SFX_DIR / "catalog.json"
    if not opts.get("sfx", True) or not cat_f.exists():
        return [], ("no SFX catalog at " + str(cat_f) if opts.get("sfx", True) else "SFX off")
    cat = json.load(open(cat_f, encoding="utf-8"))

    def pick(words, n):
        cands = [e for e in cat if any(w in Path(e["file"]).name.lower() for w in words)]
        return cands[n % len(cands)] if cands else None

    gain = -14 - (mix_lufs if mix_lufs is not None else -18)
    cues = []
    for ev_t, words, target in ((0.05, ["whoosh", "swish"], -14), (0.15, ["pop", "click"], -12),
                                (max(0, total_s - 1.6), ["pop", "click"], -12)):
        e = pick(words, len(cues))
        if not e:
            continue
        vol = 10 ** ((target - gain - e["peak_dbfs"]) / 20)
        cues.append({"file": e["file"], "start": max(0.0, ev_t - e["peak_s"]), "vol": round(min(vol, 1.0), 4)})
    return cues, None


def render_clip(clip_id, layout="auto", top_stamp="", credit=None, game_center=None,
                caption_y=None, punch=True, hook_zoom=True, sfx=True, font="DejaVu Sans"):
    c = db.one("SELECT * FROM clips WHERE id=?", clip_id)
    job = db.one("SELECT * FROM jobs WHERE id=?", c["job_id"])
    d = Path(c["dir"])
    data = db.clip_data(clip_id)
    if not data.get("source_size"):
        data["source_size"] = list(media.video_size(str(d / "cut.mp4")))
    opts = {"game_center": game_center}
    data["opts"] = opts
    if layout == "auto":
        layout = choose_layout(data)
    if layout == "split" and not data.get("facecam"):
        raise RuntimeError("split layout needs a facecam — run detect_facecam or choose 'gameplay'")
    cut = json.load(open(d / "cut.json", encoding="utf-8"))
    spans, f0 = [], 0
    for p in cut["pieces"]:
        nf = max(1, round(p["dur"] * FPS))
        spans.append((f0, nf))
        f0 += nf
    total_s = f0 / FPS
    # geometry
    W, H = data["source_size"]
    if layout == "split":
        g = _split_geometry(data, opts)
        cap_y = caption_y or g["h_game"] + LANE // 2
        regions = {"game": [CW, g["game_card_h"], 0, g["game_y"]],
                   "face": [g["wf"], g["hf"], g["face_x"], g["face_y"]]}
        face_band = [g["face_y"], g["face_y"] + g["hf"]]
    elif layout == "full":
        g = {}
        face = data.get("full_frame_face") or data.get("face")
        sc = CH / H
        if face:
            chin = (face[1] + face[3] * 1.15) * sc
            top = (face[1] - 0.3 * face[3]) * sc
        else:
            chin, top = CH * 0.45, CH * 0.2
        cap_y = caption_y or int(min(1400, max(1150, chin + 180)))
        regions = {"frame": [CW, CH, 0, 0]}
        face_band = [int(max(0, top)), int(min(CH, chin))]
    else:
        sc = min(GAME_SCALE_MAX, CW / W)
        card_h = _even(H * sc)
        g = {"card_y": max(240, (CH - card_h) // 2 - 120)}
        cap_y = caption_y or int(min(1400, g["card_y"] + card_h + 110))
        regions = {"game": [_even(W * sc), card_h, (CW - _even(W * sc)) // 2, g["card_y"]]}
        face_band = None
    # pass 1: layout per piece, punch alternation (static per piece, never moving at a cut)
    chains = []
    for i, (s0, nf) in enumerate(spans):
        k = PUNCH if (punch and i % 2 == 1) else 1.0
        chains.append(_piece_filter(i, s0, nf, layout, g, data, k))
    graph = ";".join(chains) + ";" + "".join(f"[p{i}]" for i in range(len(spans))) + \
        f"concat=n={len(spans)}:v=1:a=0,fps={FPS},format=yuv420p[v]"
    comp = d / "composed.mp4"
    media.run(["ffmpeg", "-v", "error", "-y", "-i", d / "cut.mp4", "-filter_complex", graph,
               "-map", "[v]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "14", "-r", str(FPS), comp])
    # captions / stamps / credit
    caps = json.load(open(d / "captions.json", encoding="utf-8")) if (d / "captions.json").exists() else []
    if credit is None:
        who = job.get("streamer") or "the streamer"
        where = job.get("platform") or "stream"
        credit = f"Clipped from {who} · live on {where}"
    ass_path = d / "overlay.ass"
    ass_path.write_text(_ass(caps, cap_y, total_s, top_stamp, credit, font), encoding="utf-8")
    # overlay alone, with alpha (for the face guard)
    media.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
               f"color=black:s={CW}x{CH}:r={FPS}:d={total_s:.3f}", "-vf",
               f"ass={ass_path.name},format=rgba,colorkey=0x000000:0.02:0", "-c:v", "qtrle",
               "overlay.mov"], cwd=d)
    # audio: SFX + two-pass loudnorm with encoder headroom (TP −3)
    mix_lufs, _ = media.loudness(str(d / "cut_mix.wav"))
    cues, sfx_note = _sfx_plan(mix_lufs, total_s, {"sfx": sfx})
    premix = d / "premix.wav"
    if cues:
        cmd = ["ffmpeg", "-v", "error", "-y", "-i", d / "cut_mix.wav"]
        fl = []
        for j, q in enumerate(cues):
            cmd += ["-i", q["file"]]
            ms = int(q["start"] * 1000)
            fl.append(f"[{j + 1}:a]aresample=48000,aformat=channel_layouts=stereo,volume={q['vol']},"
                      f"adelay={ms}|{ms}[s{j}]")
        fl.append("[0:a]" + "".join(f"[s{j}]" for j in range(len(cues))) +
                  f"amix=inputs={len(cues) + 1}:normalize=0:duration=first[a]")
        media.run(cmd + ["-filter_complex", ";".join(fl), "-map", "[a]", "-ar", "48000", premix])
    else:
        media.run(["ffmpeg", "-v", "error", "-y", "-i", d / "cut_mix.wav", "-ar", "48000", premix])
    meas = media.run(["ffmpeg", "-hide_banner", "-i", premix, "-af",
                      "loudnorm=I=-14:TP=-3.0:LRA=11:print_format=json", "-f", "null", "-"]).stderr
    js = json.loads(meas[meas.rfind("{"):meas.rfind("}") + 1])
    ln = (f"loudnorm=I=-14:TP=-3.0:LRA=11:measured_I={js['input_i']}:measured_TP={js['input_tp']}:"
          f"measured_LRA={js['input_lra']}:measured_thresh={js['input_thresh']}:"
          f"offset={js['target_offset']}:linear=true,aresample=48000")
    # pass 2: hook zoom-out (opening only), burn the overlay, mux, trim AUDIO to video length
    vf = []
    if hook_zoom:
        z = "if(lt(t,1.667),1+0.3*pow(1-t/1.667,3),1)"
        vf.append(f"scale=w='trunc({CW}*{z}/2)*2':h='trunc({CH}*{z}/2)*2':eval=frame:flags=bicubic,"
                  f"crop={CW}:{CH}")
    vf.append(f"ass={ass_path.name}")
    vf.append("format=yuv420p")
    out = d / "final.mp4"
    media.run(["ffmpeg", "-v", "error", "-y", "-i", comp.name, "-i", premix.name, "-filter_complex",
               f"[0:v]{','.join(vf)}[v];[1:a]{ln},apad,atrim=duration={total_s:.4f}[a]",
               "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
               "-pix_fmt", "yuv420p", "-r", str(FPS), "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
               "-ac", "2", "-movflags", "+faststart", out.name], cwd=d)
    lufs, tp = media.loudness(str(out))
    db.merge_clip_data(clip_id, final=str(out), overlay=str(d / "overlay.mov"), layout=layout,
                       regions=regions, face_band=face_band, caption_y=cap_y, sfx_cues=cues,
                       top_stamp=top_stamp, credit=credit)
    db.set_clip(clip_id, status="rendered", layout=layout)
    return {"final": str(out), "layout": layout, "duration_s": round(total_s, 3), "lufs": lufs,
            "true_peak": tp, "regions": regions, "face_band": face_band, "sfx": cues or sfx_note}


def review_clip(clip_id):
    c = db.one("SELECT * FROM clips WHERE id=?", clip_id)
    d = Path(c["dir"])
    data = db.clip_data(clip_id)
    rv = d / "review"
    cmd = [__import__("sys").executable, paths.SCRIPTS["review_reel"], data["final"], "--out", rv,
           "--cut", d / "cut.json", "--sections", d / "sections.txt"]
    if (d / "captions.json").exists():
        cmd += ["--captions", d / "captions.json"]
    if data.get("voice_is_stem") and (d / "cut_voice16k.wav").exists():
        cmd += ["--voice", d / "cut_voice16k.wav"]
    if (d / "overlay.mov").exists():
        cmd += ["--overlay", d / "overlay.mov"]
        if data.get("face_band"):
            cmd += ["--face-band", f"{data['face_band'][0]}:{data['face_band'][1]}"]
    for name, (w, h, x, y) in (data.get("regions") or {}).items():
        cmd += ["--region", f"{name}:{w}:{h}:{x}:{y}"]
    p = media.run(cmd, check=False)
    rep = json.load(open(rv / "report.json", encoding="utf-8"))
    db.set_clip(clip_id, review_verdict=rep["verdict"], review_report=str(rv / "report.md"),
                status="reviewed")
    return {"verdict": rep["verdict"], "report": str(rv / "report.md"),
            "sheets": [str(rv / "sheet_mid.jpg"), str(rv / "sheet_post.jpg")],
            "fails": [f"{r['check']}: {r['summary']}" for r in rep["checks"] if r["status"] == "FAIL"],
            "warns": [f"{r['check']}: {r['summary']}" for r in rep["checks"] if r["status"] == "WARN"],
            "skips": [r["check"] for r in rep["checks"] if r["status"] == "SKIP"]}
