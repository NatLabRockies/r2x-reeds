// Preserve bookmarks when moving former Sphinx pages into the current guide tree.
(async () => {
  const destination = document.querySelector('link[rel="canonical"]').getAttribute('href');
  const fragment = window.location.hash;
  let target = destination + fragment;
  if (window.location.pathname.endsWith('/references/api.html') && fragment) {
    try {
      const response = await fetch('/r2x-reeds/api-fragments.json');
      if (!response.ok) throw new Error(`API fragment map: HTTP ${response.status}`);
      const members = await response.json();
      target = members[decodeURIComponent(fragment.slice(1))] ?? target;
    } catch (error) {
      console.warn('Could not resolve the API member bookmark', error);
    }
  }
  window.location.replace(target);
})();
