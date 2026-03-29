# ✨ Tycho

**Surface hidden gems. Star-powered promos from archival content.**

---

## The Pitch

Remember when Brad Pitt was just a teenager on that 80s show you love? Or when Julia Roberts had a tiny role in something nobody remembers?

**Tycho finds those moments automatically.**

Streaming services sit on decades of content with future-famous actors in early roles. Fans of their later work don't know these gems exist. Existing trailers don't highlight them.

Tycho changes that:
1. Takes any video you own
2. Finds every actor in it (using their headshots)
3. Generates a promo spot focused on each star

**Example output:**
> *"Did you know Doug Smith appeared on Season 4 of That Funny Show when he was a teenager? Watch him early in his career, only on MediaPlus+."*

Perfect for:
- Streaming platforms with archival content
- Marketing teams maximizing catalog value
- Fan engagement campaigns

---

## Setup (2 minutes)

### 1. Get API Keys (free)
- **12Labs:** https://playground.twelvelabs.io/ (video search)
- **LTX:** https://ltx.studio/ (video generation)

### 2. Create `.env` file
```bash
TWELVE_LABS_API_KEY=your_key_here
LTX_API_KEY=your_key_here
```

### 3. Install & Run
```bash
pip install twelvelabs fastapi uvicorn python-dotenv requests

python api.py
python -m http.server 3000
```

### 4. Open Browser
http://localhost:3000

Enter `tt0058331` (Mary Poppins) and click **Find Content**.

---

## Demo

**Use the included `coke.mp4` with Mary Poppins (1964):**

1. Open http://localhost:3000
2. IMDb ID: `tt0058331`
3. Video: `coke.mp4`
4. Click **Find Content**
5. Click **Generate Spot** for any actor

Watch the magic happen. 🎬

---

## Built With

- **IMDb** (imdbapi.dev) - Cast data & headshots
- **12Labs** - Find actors in video via visual search
- **LTX** - AI video generation
- **FastAPI** - Backend API

---

**Hackathon ready. Questions? Just ask.** 🚀
