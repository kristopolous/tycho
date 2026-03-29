<p align="center">
<img width="598" height="183" alt="logo" src="https://github.com/user-attachments/assets/a8212683-d3c5-49e0-8375-9c96ab93abc4" />
<br/>
<strong>Surface hidden gems. Star-powered promos from archival content.</strong>
</p>

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

python app.py
```

### 4. Open Browser
The app will display the port (starts at 8000):
```
Starting Tycho API on port 8000...
```

Go to http://localhost:8000

Enter `tt0310917` (The Day After Tomorrow) and click **Find Content**.

---

## Demo

**Use your own `content.mp4` with The Day After Tomorrow (2004):**

1. Place your video file as `content.mp4` in the project directory
2. Open http://localhost:3000
3. IMDb ID: `tt0310917`
4. Video: `content.mp4`
5. Click **Find Content**
6. Click **Generate Spot** for any actor

Watch the magic happen. 🎬

---

## Built With

- **IMDb** (imdbapi.dev) - Cast data & headshots
- **12Labs** - Find actors in video via visual search
- **LTX** - AI video generation
- **Bedrock** - Amazong Bedrock
