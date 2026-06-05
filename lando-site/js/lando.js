/* Lando Norris site — motion & interactions */

// Loader
window.addEventListener("load", () => {
  setTimeout(() => {
    document.querySelector(".loader")?.classList.add("is-done");
  }, 1600);
});

// Nav scroll + mobile
const nav = document.querySelector(".nav");
window.addEventListener("scroll", () => {
  nav?.classList.toggle("is-scrolled", window.scrollY > 50);
}, { passive: true });

document.querySelector(".nav__burger")?.addEventListener("click", () => {
  nav?.classList.toggle("is-open");
});

// Scroll reveal
const revealObs = new IntersectionObserver(
  (entries) => {
    entries.forEach((e) => {
      if (e.isIntersecting) {
        e.target.classList.add("is-visible");
        revealObs.unobserve(e.target);
      }
    });
  },
  { threshold: 0.1, rootMargin: "0px 0px -60px 0px" }
);

document.querySelectorAll("[data-reveal], [data-reveal-left]").forEach((el) => {
  revealObs.observe(el);
});

// Marquee duplicate
document.querySelectorAll(".marquee-strip__track").forEach((track) => {
  if (!track.dataset.cloned) {
    track.dataset.cloned = "1";
    track.innerHTML += track.innerHTML;
  }
});

// Horizontal drag scroll
document.querySelectorAll(".h-scroll__track").forEach((track) => {
  let isDown = false;
  let startX;
  let scrollLeft;

  track.addEventListener("mousedown", (e) => {
    isDown = true;
    track.classList.add("is-dragging");
    startX = e.pageX - track.offsetLeft;
    scrollLeft = track.scrollLeft;
  });

  track.addEventListener("mouseleave", () => {
    isDown = false;
    track.classList.remove("is-dragging");
  });

  track.addEventListener("mouseup", () => {
    isDown = false;
    track.classList.remove("is-dragging");
  });

  track.addEventListener("mousemove", (e) => {
    if (!isDown) return;
    e.preventDefault();
    const x = e.pageX - track.offsetLeft;
    track.scrollLeft = scrollLeft - (x - startX) * 1.5;
  });
});

// Parallax hero car
const heroCar = document.querySelector(".hero__car");
if (heroCar) {
  window.addEventListener("scroll", () => {
    const y = window.scrollY * 0.15;
    heroCar.style.transform = `translateY(${y}px)`;
  }, { passive: true });
}

// Stat counter
function animateValue(el, end, suffix = "") {
  const duration = 1800;
  const start = performance.now();
  const ease = (t) => 1 - Math.pow(1 - t, 4);

  function tick(now) {
    const p = Math.min((now - start) / duration, 1);
    const val = Math.round(end * ease(p));
    el.textContent = val + suffix;
    if (p < 1) requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}

document.querySelectorAll("[data-count]").forEach((el) => {
  const end = parseInt(el.dataset.count, 10);
  const suffix = el.dataset.suffix || "";
  const obs = new IntersectionObserver(([entry]) => {
    if (entry.isIntersecting) {
      animateValue(el, end, suffix);
      obs.unobserve(el);
    }
  }, { threshold: 0.5 });
  obs.observe(el);
});
