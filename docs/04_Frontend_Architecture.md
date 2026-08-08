🎨 Frontend Architecture (Vanilla PWA)

AI Context: No React/Vue. Vanilla HTML5, CSS3, JS. Served as Django templates, but highly API-driven using fetch().

CSS Guidelines (Flamingo / Miami / Duolingo Vibe)

The aesthetic is "Miami Vice meets Duolingo." It uses bright neon pastel colors, chunky shapes, heavy font weights, and bouncy animations. Everything should feel tactile and gamified.

Color Palette (CSS Variables in :root):

--primary-pink: #FF5E9A; (Primary actions, Flamingo mascot color)

--dark-pink: #D83A78; (For button bottom borders/shadows)

--primary-orange: #FF9933; (Streaks, Fire icons, warnings)

--primary-blue: #00E5FF; (Endurance nodes, cool accents)

--primary-purple: #9D4EDD; (Strength nodes, Boss Fights)

--bg-light: #FFFFFF; (Card backgrounds)

--bg-app: #FDF4F7; (Slightly warm, pinkish-white background for the whole app)

--text-main: #2B2B2B;

--text-muted: #8E8E8E;

Typography:

Use a rounded, heavy sans-serif font like 'Nunito', 'Varela Round', or 'Quicksand'.

Headers should be highly legible, bold, and playful.

Shapes & Structure:

Everything is a card. border-radius: 20px; is the standard.

Heavy use of Flexbox for center alignment.

Buttons (The "Duolingo Pop"):
Buttons must have a 3D tactile feel using thick bottom borders that compress when clicked.

.btn-flamingo {
    background-color: var(--primary-pink);
    color: white;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 1px;
    padding: 16px 24px;
    border: none;
    border-bottom: 5px solid var(--dark-pink);
    border-radius: 16px;
    cursor: pointer;
    transition: transform 0.1s, border-bottom 0.1s;
}
.btn-flamingo:active {
    transform: translateY(5px);
    border-bottom: 0px solid var(--dark-pink);
    margin-bottom: 5px; /* prevents layout shift on click */
}


PWA Requirements

Root must include a valid manifest.json.

A vanilla JS service-worker.js must be registered to cache static assets (CSS/JS/Icons) to ensure instant loading on mobile.

UI must be Mobile-First. Wrap the main view in a container with max-width: 480px; margin: 0 auto; for desktop users to maintain the app feel.