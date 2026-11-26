import textwrap, subprocess
from PIL import Image, ImageDraw, ImageFont
W,H=1280,720
mono=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",17)
big=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",26)
mid=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",21)
src=open("/tmp/entry/flagsmith-migrate-parity/docs/demo-run.txt").read().splitlines()
src=[l for l in src if l.strip()]
COLS=118; ROWS=24; LH=23
frames=[]  # (image, seconds)
def card(lines,secs):
    im=Image.new("RGB",(W,H),(18,20,28)); d=ImageDraw.Draw(im); y=170
    for i,t in enumerate(lines):
        for w in (textwrap.wrap(t,52 if i==0 else 84) or [""]):
            d.text((70,y),w,font=big if i==0 else mid,fill=(240,240,240) if i==0 else (190,200,215)); y+=40 if i==0 else 32
    frames.append((im,secs))
card(["Moving feature flags to Flagsmith without changing who gets what","","A 30% rollout is still 30% after a migration.","But is it the same 30% of users?","","Flagsmith CLI agent skill: flagsmith-migrate-parity","This video is a terminal replay of recorded output (docs/demo-run.txt), not a live capture. Local self-hosted Flagsmith, reference app."],5)
caption=""
buf=[]
def render(cap):
    im=Image.new("RGB",(W,H),(12,14,20)); d=ImageDraw.Draw(im)
    d.rectangle([0,0,W,52],fill=(30,36,52)); d.text((24,13),cap,font=mid,fill=(255,214,102))
    y=70
    vis=buf[-ROWS:]
    for t,c in vis:
        d.text((24,y),t,font=mono,fill=c); y+=LH
    return im
def color(l):
    if l.startswith("$"): return (120,200,255)
    if l.startswith("#"): return (255,214,102)
    if any(k in l for k in ('"MISMATCHES"','CLOSED','mismatch":3','mismatch":2')): return (255,120,120)
    if any(k in l for k in ('PARITY_ON_SAMPLE','OPEN_FOR_HUMAN')): return (130,230,140)
    return (215,215,215)
for l in src:
    if l.startswith("### "): caption=l[4:]
    if l.startswith("(a human"): caption="Stop: a human approves the switch. The tool never switches the app."
    if l.startswith("$ fsmig gate"): caption=(caption+"  |  gate").strip()
    for w in (textwrap.wrap(l,COLS,subsequent_indent="  ") or [""]):
        buf.append((w,color(l)))
    if l.startswith("$") : secs=1.4
    elif l.startswith("#") : secs=1.0
    else: secs=min(7.5,2.5+len(l)/70)
    if "MISMATCHES" in l or "OPEN_FOR_HUMAN" in l or "CLOSED" in l or "PARITY_ON" in l: secs+=2
    frames.append((render(caption or "inventory"),secs))
card(["What this shows","","Per-user replay catches what totals hide: in this run 345 of 800 users differed on fast-search in native mode while enabled counts were 255 vs 240. Counts vary by project.","Preserve mode matched on the sample (0 mismatches), at the cost of sending a legacy-bucket trait.","","Limits: reference app, sampled identities only. Not tested: multivariate, segment priority,","identity overrides, multiple environments, Flagsmith Cloud. Not a production migration."],7)
with open("list.txt","w") as f:
    for i,(im,s) in enumerate(frames):
        p=f"f/{i:03d}.png"; im.save(p); f.write(f"file '{p}'\nduration {s:.2f}\n")
    f.write(f"file 'f/{len(frames)-1:03d}.png'\n")
print(len(frames), sum(s for _,s in frames))
