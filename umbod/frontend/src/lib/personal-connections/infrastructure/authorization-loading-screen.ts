export function renderAuthorizationLoadingScreen(popup: Window, displayName: string): void {
  const document = popup.document;
  document.documentElement.lang = 'en';

  const title = document.createElement('title');
  title.textContent = `Connecting to ${displayName} · Umbod`;

  const viewport = document.createElement('meta');
  viewport.name = 'viewport';
  viewport.content = 'width=device-width, initial-scale=1';

  const style = document.createElement('style');
  style.textContent = `
    :root {
      color-scheme: light;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: #14201c;
      background: #f4f7f5;
      font-synthesis: none;
      -webkit-font-smoothing: antialiased;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      min-height: 100dvh;
      display: grid;
      place-items: center;
      padding: 24px 16px;
      background: radial-gradient(ellipse at top, #e3efe7, #f4f7f5 72%);
    }
    main {
      width: 100%;
      max-width: 440px;
      padding: clamp(24px, 7vw, 40px);
      border: 1px solid #dce4df;
      border-radius: 24px;
      background: #fff;
      box-shadow: 0 20px 64px #14201c0d;
      text-align: center;
      overflow-wrap: anywhere;
    }
    .brand {
      display: flex;
      justify-content: center;
      align-items: center;
      gap: 10px;
      margin-bottom: 36px;
      font-size: 19px;
      font-weight: 650;
      letter-spacing: -0.5px;
    }
    .monogram {
      display: grid;
      place-items: center;
      width: 34px;
      height: 34px;
      border-radius: 11px;
      background: #07634e;
      color: #fff;
      font-size: 21px;
    }
    .spinner {
      width: 36px;
      height: 36px;
      margin: 0 auto 24px;
      border: 3px solid #dce4df;
      border-top-color: #07634e;
      border-radius: 50%;
      animation: spin 1s linear infinite;
    }
    h1 {
      margin: 0 0 16px;
      font-size: clamp(23px, 6vw, 28px);
      line-height: 1.25;
      letter-spacing: -0.7px;
    }
    p { margin: 0; font-size: 15px; line-height: 1.65; }
    .secondary {
      margin-top: 28px;
      padding-top: 24px;
      border-top: 1px solid #dce4df;
      color: #52645b;
      font-size: 13px;
    }
    @keyframes spin { to { transform: rotate(360deg); } }
    @media (prefers-reduced-motion: reduce) {
      .spinner { animation: none; }
    }
  `;

  const card = document.createElement('main');
  const brand = document.createElement('div');
  brand.className = 'brand';
  const monogram = document.createElement('span');
  monogram.className = 'monogram';
  monogram.setAttribute('aria-hidden', 'true');
  monogram.textContent = 'U';
  const brandName = document.createElement('span');
  brandName.textContent = 'Umbod';
  brand.append(monogram, brandName);

  const spinner = document.createElement('div');
  spinner.className = 'spinner';
  spinner.setAttribute('aria-hidden', 'true');

  const status = document.createElement('div');
  status.setAttribute('role', 'status');
  status.setAttribute('aria-live', 'polite');
  const heading = document.createElement('h1');
  heading.textContent = `Connecting to ${displayName}…`;
  status.append(heading);

  const explanation = document.createElement('p');
  explanation.textContent = "Complete sign-in here. This window will close automatically when you're done.";
  const secondary = document.createElement('p');
  secondary.className = 'secondary';
  secondary.textContent = "You can return to Umbod to cancel or try again if sign-in doesn't open.";

  card.append(brand, spinner, status, explanation, secondary);
  document.head.replaceChildren(title, viewport, style);
  document.body.replaceChildren(card);
}
