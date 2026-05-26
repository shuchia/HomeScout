# HomeScout Touring Pipeline - User Guide

From discovering an apartment to deciding where to apply, HomeScout's touring pipeline tracks every step of your apartment hunt.

---

## The Journey at a Glance

```
Search & Favorite  ->  Start Touring  ->  Plan & Prepare  ->  Tour & Capture  ->  Decide & Apply
```

---

## Step 1: Save Apartments You Like

Start on the **Search** page. When you find an apartment that catches your eye, tap the **heart icon** to save it to your Favorites.

Head to the **Favorites** page to see everything you've saved. Each card shows the apartment's address, rent, beds/baths, amenities, and photos.

---

## Step 2: Start Touring

Below each favorited apartment, you'll see a **"Start Touring"** button. Tap it to add the apartment to your tour pipeline. The button turns green and shows **"In Tours"** once it's added.

This creates a tour entry in the **"Interested"** stage -- you're tracking it now.

---

## Step 3: The Tours Dashboard

Navigate to **Tours** (via the header link or the bottom tab bar on mobile). This is your command center.

### Three tabs organize your tours:

- **Today** -- Tours scheduled for today, sorted by time
- **Upcoming** -- Future scheduled tours, sorted by date
- **All** -- Every tour grouped by stage

### Smart banners appear when relevant:

- **"N apartments have an email draft ready"** -- Apartments in the Interested stage where you haven't sent outreach yet
- **Day Planner** -- Appears when you have 2+ tours on the same day (Pro feature)
- **Decision Brief** -- Appears when you've toured 2+ apartments (Pro feature)

Each tour shows as a compact card with the address, rent, stage badge, and any ratings or notes you've added.

---

## Step 4: Prepare -- Send an Inquiry Email (Pro)

Tap a tour card to open the **Tour Detail** page. Switch to the **Email** tab.

**Pro users:** Tap **"Generate Inquiry Email"** and Claude AI writes a personalized email to the landlord. The email:
- References the specific listing details
- Mentions your move-in date and requirements
- Asks smart questions about information missing from the listing (no square footage listed? It asks. You mentioned pets but no pet policy? It asks about that too.)

Tap **"Copy"** to copy the email to your clipboard, then paste it into your email app and send. You can also tap **"Regenerate"** for a different version.

**Free users:** See the basic pipeline tracking but get an upgrade prompt for AI email generation.

---

## Step 5: Schedule Your Tours

Update your tour entries with scheduled dates and times. The dashboard automatically groups tours by date in the **Today** and **Upcoming** tabs.

### Day Planner (Pro)

When you have 2+ tours on the same day, a **"Plan This Day"** card appears. Tap it and Claude AI analyzes your tour addresses to:

- Suggest the **optimal visiting order** to minimize travel
- Estimate **travel times** between stops
- Provide **tips** like "These two are 3 blocks apart -- book back-to-back"

---

## Step 6: Tour Day -- Capture Everything

This is where HomeScout shines. During (or right after) a tour, open the tour detail page and switch to the **Capture** tab. Everything you need is here:

### Rate It (Stars)

Tap 1-5 stars for a quick overall impression. Setting a rating **automatically advances** the tour from "Scheduled" to "Toured" stage.

### Tag It (Quick Tags)

Tap suggested tags like **"Great light"**, **"Spacious"**, or **"Small kitchen"** to quickly capture pros and cons. Tags are color-coded:
- **Green** = Pro (things you liked)
- **Red** = Con (things that concerned you)

Tap **"+ Custom"** to add your own tags with a pro or con sentiment.

### Voice Notes (Hold to Talk)

The big **"Hold to Record"** button is designed for one-thumb use while you're walking through an apartment:

1. **Press and hold** the button
2. A red pulsing dot and timer appear while you talk
3. **Release** when you're done
4. Your audio uploads to the cloud
5. **"Transcribing..."** appears while OpenAI Whisper converts speech to text
6. The transcribed text replaces the placeholder within seconds

**Pro users** get automatic note enhancement -- Claude cleans up filler words, structures your observations, and suggests relevant tags.

Voice notes show with a **microphone icon**; typed notes show with a **pencil icon**.

### Typed Notes

For quieter moments (maybe after the tour, back at home), use the text area to type detailed notes. Tap **"Add"** or press Shift+Enter to save.

### Photos

View any photos you've captured for this tour. (Photo upload integration coming soon.)

---

## Step 7: After All Your Tours -- Decide

Once you've toured 2+ apartments, the **Decision Brief** banner appears on your Tours dashboard.

### AI Decision Brief (Pro)

Tap **"Get AI Recommendation"** and Claude synthesizes everything -- your ratings, tags, notes, and the listing data -- into a clear analysis:

- **Per-apartment cards** showing:
  - Your star rating
  - AI's take on the apartment
  - **Strengths** (green) -- what makes this one stand out
  - **Concerns** (red) -- what to watch out for
  - A **"Top Pick"** badge on the recommended winner

- **Final recommendation** at the bottom explaining why one apartment is the best fit for you, respecting your own ratings and impressions.

---

## Step 8: Apply or Pass

On any toured apartment's detail page, a **sticky decision bar** appears at the bottom with three buttons:

- **Applied** (green) -- You're going for it
- **Pass** (gray) -- Not the right fit
- **Undecided** (outline) -- Still thinking

Tap to set your decision. Tap again to change your mind. The decision shows as a badge on your tour card in the dashboard.

---

## Post-Tour Reminders

30 minutes after a scheduled tour time, HomeScout creates a **reminder notification**: "How was your tour? Tap to rate and capture your impressions." This nudges you to capture your fresh impressions before you forget.

---

## Mobile Experience

HomeScout is designed mobile-first for apartment hunting on the go:

- **Bottom navigation bar** (Home / Tours / Favorites) for quick switching
- **Hold-to-talk** voice recording works with touch events
- **Large tap targets** on stars, tags, and buttons
- **Single-column layouts** optimized for phone screens
- Everything works on desktop too -- the bottom nav hides and layouts expand

---

## Free vs Pro Features

| Feature | Free | Pro |
|---------|------|-----|
| Tour pipeline tracking | Yes | Yes |
| Star ratings | Yes | Yes |
| Pro/con tags | Yes | Yes |
| Typed notes | Yes | Yes |
| Voice notes + transcription | Yes | Yes |
| Photos | Yes | Yes |
| **AI inquiry email generation** | -- | Yes |
| **AI day planner (route optimization)** | -- | Yes |
| **AI note enhancement** | -- | Yes |
| **AI decision brief + recommendation** | -- | Yes |

Free users get the full manual pipeline. Pro users get Claude AI at every stage -- drafting emails, optimizing tour days, cleaning up notes, and synthesizing a final recommendation.

---

## Pipeline Stages Reference

| Stage | How you get here | What you can do |
|-------|-----------------|-----------------|
| **Interested** | Click "Start Touring" on a favorite | Generate inquiry email, schedule tour |
| **Outreach Sent** | Mark outreach as sent | Wait for response, schedule tour |
| **Scheduled** | Set a tour date and time | Plan your day, prepare questions |
| **Toured** | Rate the apartment (auto-advances) or manually update | Capture notes/tags/photos, compare with others |
| **Deciding** | Automatic when 2+ tours are completed | Get AI decision brief, make final call |

Stages are **skippable** -- if you already have a tour scheduled, you can jump straight to "Scheduled" without going through "Outreach Sent."
