/* Kurawa — Framer-style motion */

const nav = document.querySelector(".nav");
if (nav) {
  const onScroll = () => nav.classList.toggle("is-scrolled", window.scrollY > 24);
  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();
}

document.querySelector(".nav__burger")?.addEventListener("click", () => {
  nav?.classList.toggle("is-open");
});

// Scroll reveal (Framer fade-up)
const revealOpts = { threshold: 0.12, rootMargin: "0px 0px -48px 0px" };
const revealObs = new IntersectionObserver((entries) => {
  entries.forEach((e) => {
    if (e.isIntersecting) {
      e.target.classList.add("is-visible");
      revealObs.unobserve(e.target);
    }
  });
}, revealOpts);

document.querySelectorAll("[data-reveal], [data-reveal-stagger], [data-blur-in]").forEach((el) => {
  revealObs.observe(el);
});

// Counter animation
function animateCounter(el, target, suffix = "") {
  const duration = 2000;
  const start = performance.now();
  const from = 0;
  const ease = (t) => 1 - Math.pow(1 - t, 4);

  function frame(now) {
    const p = Math.min((now - start) / duration, 1);
    const val = Math.round(from + (target - from) * ease(p));
    el.textContent = val.toLocaleString() + suffix;
    if (p < 1) requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
}

document.querySelectorAll("[data-counter]").forEach((el) => {
  const target = parseInt(el.dataset.counter, 10);
  const suffix = el.dataset.suffix || "";
  const counterObs = new IntersectionObserver(([entry]) => {
    if (entry.isIntersecting) {
      animateCounter(el, target, suffix);
      counterObs.unobserve(el);
    }
  }, { threshold: 0.5 });
  counterObs.observe(el);
});

// Hero carousel
const carousel = document.querySelector(".hero__carousel-inner");
const slides = document.querySelectorAll(".hero__slide");
let slideIndex = 0;

function goSlide(dir) {
  if (!carousel || !slides.length) return;
  slideIndex = (slideIndex + dir + slides.length) % slides.length;
  carousel.style.transform = `translateX(-${slideIndex * 100}%)`;
}

document.querySelector(".carousel-prev")?.addEventListener("click", () => goSlide(-1));
document.querySelector(".carousel-next")?.addEventListener("click", () => goSlide(1));

if (slides.length > 1) {
  setInterval(() => goSlide(1), 5000);
}

// Rotating ship CTA words
const words = ["Website", "SaaS", "Business", "E-commerce"];
let wordIdx = 0;
const wordEl = document.querySelector(".ship-cta__rotating");

if (wordEl) {
  const cycle = () => {
    wordEl.classList.remove("is-active");
    setTimeout(() => {
      wordIdx = (wordIdx + 1) % words.length;
      wordEl.textContent = words[wordIdx];
      wordEl.classList.add("is-active");
    }, 400);
  };
  wordEl.classList.add("is-active");
  setInterval(cycle, 2800);
}

// FAQ
document.querySelectorAll(".faq-item button").forEach((btn) => {
  btn.addEventListener("click", () => {
    const item = btn.closest(".faq-item");
    const open = item.classList.contains("is-open");
    document.querySelectorAll(".faq-item").forEach((i) => i.classList.remove("is-open"));
    if (!open) item.classList.add("is-open");
  });
});

// Duplicate marquee rows for seamless loop
document.querySelectorAll(".tweet-row, .logos-marquee-wrap").forEach((wrap) => {
  const row = wrap.querySelector(".tweet-row, .logos-marquee");
  if (row && !row.dataset.cloned) {
    row.dataset.cloned = "1";
    row.innerHTML += row.innerHTML;
  }
});

// Smooth hover magnetic buttons (subtle)
document.querySelectorAll(".btn--dark").forEach((btn) => {
  btn.addEventListener("mousemove", (e) => {
    const r = btn.getBoundingClientRect();
    const x = (e.clientX - r.left - r.width / 2) * 0.08;
    const y = (e.clientY - r.top - r.height / 2) * 0.08;
    btn.style.transform = `translate(${x}px, ${y}px)`;
  });
  btn.addEventListener("mouseleave", () => {
    btn.style.transform = "";
  });
});
