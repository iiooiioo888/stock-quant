function createBus() {
  const target = new EventTarget();
  return {
    on(type, handler, opts) {
      if (!type || !handler) return () => {};
      target.addEventListener(type, handler, opts);
      return () => {
        try { target.removeEventListener(type, handler, opts); } catch (_) {}
      };
    },
    emit(type, detail) {
      if (!type) return;
      try {
        target.dispatchEvent(new CustomEvent(type, { detail }));
      } catch (_) {
        // Older browsers fallback
        const ev = document.createEvent('CustomEvent');
        ev.initCustomEvent(type, false, false, detail);
        target.dispatchEvent(ev);
      }
    },
  };
}

export const bus = createBus();

