// Shared progressive enhancements. Navigation and content are built into HTML.
    const menu = document.getElementById('mobile-menu');
    const menuToggle = document.querySelector('.menu-toggle');
    const mobileLayout = window.matchMedia('(max-width: 760px)');

    // Use the same community destinations and icons in both navigation layouts.
    const mobileCommunity = menu.querySelector('.mobile-community');
    for (const link of document.querySelectorAll('.community-nav a')) {
      const mobileLink = link.cloneNode(true);
      mobileLink.removeAttribute('class');
      mobileLink.append(document.createTextNode(link.title));
      mobileCommunity.append(mobileLink);
    }

    menuToggle.addEventListener('click', () => {
      if (!mobileLayout.matches) return;
      menu.showModal();
      menuToggle.setAttribute('aria-expanded', 'true');
    });
    menu.querySelector('.menu-close').addEventListener('click', () => menu.close());
    menu.addEventListener('close', () => menuToggle.setAttribute('aria-expanded', 'false'));
    menu.addEventListener('click', (event) => {
      if (event.target.closest('a')) {
        menu.close();
      } else if (event.target === menu) {
        const bounds = menu.getBoundingClientRect();
        if (event.clientX < bounds.left || event.clientX > bounds.right ||
            event.clientY < bounds.top || event.clientY > bounds.bottom) menu.close();
      }
    });
    mobileLayout.addEventListener('change', () => {
      if (!mobileLayout.matches && menu.open) {
        menu.close();
        document.querySelector('.nav-links a').focus({ preventScroll: true });
      }
    });

    const status = document.getElementById('copy-status');
    for (const button of document.querySelectorAll('[data-copy-target]')) {
      let resetTimer;
      button.addEventListener('click', async () => {
        const target = document.getElementById(button.dataset.copyTarget);
        if (!target) return;
        clearTimeout(resetTimer);
        try {
          await navigator.clipboard.writeText(target.textContent);
          button.textContent = 'Copied';
          status.textContent = 'Command copied to clipboard.';
        } catch {
          button.textContent = 'Select text';
          status.textContent = 'Could not access the clipboard. Select and copy the command below.';
          const selection = window.getSelection();
          const range = document.createRange();
          range.selectNodeContents(target);
          selection.removeAllRanges();
          selection.addRange(range);
          target.closest('pre').focus();
        }
        resetTimer = setTimeout(() => { button.textContent = 'Copy'; }, 2400);
      });
    }

document.querySelectorAll('a[href="/enterprise/"]').forEach(link => {
  if (location.pathname.startsWith("/enterprise")) link.setAttribute("aria-current", "page");
});
