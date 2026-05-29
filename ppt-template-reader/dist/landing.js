const reveals = document.querySelectorAll(".reveal");
const ambient = document.querySelector(".ambient");
const typingText = document.querySelector("#typingText");
const magneticItems = document.querySelectorAll(".magnetic");

const observer = new IntersectionObserver(
  (entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add("visible");
      }
    });
  },
  { threshold: 0.18 }
);

reveals.forEach((item) => observer.observe(item));

window.addEventListener("pointermove", (event) => {
  const x = Math.round((event.clientX / window.innerWidth) * 100);
  const y = Math.round((event.clientY / window.innerHeight) * 100);
  ambient?.style.setProperty("--mx", `${x}%`);
  ambient?.style.setProperty("--my", `${y}%`);
});

magneticItems.forEach((item) => {
  item.addEventListener("pointermove", (event) => {
    const rect = item.getBoundingClientRect();
    const x = event.clientX - rect.left - rect.width / 2;
    const y = event.clientY - rect.top - rect.height / 2;
    item.style.transform = `translate(${x * 0.12}px, ${y * 0.18}px) scale(1.03)`;
  });

  item.addEventListener("pointerleave", () => {
    item.style.transform = "";
  });
});

const prompts = [
  "Build a launch deck from this messy idea and make it feel cinematic.",
  "Extract the story, generate the headings, and map it into the best template.",
  "Trim the repetition. Keep the drama. Export a presentation-ready PowerPoint.",
];

let promptIndex = 0;
let charIndex = 0;
let deleting = false;

function tickTyping() {
  if (!typingText) return;

  const prompt = prompts[promptIndex];
  typingText.textContent = prompt.slice(0, charIndex);

  if (!deleting && charIndex < prompt.length) {
    charIndex += 1;
    setTimeout(tickTyping, 34);
    return;
  }

  if (!deleting && charIndex === prompt.length) {
    deleting = true;
    setTimeout(tickTyping, 1400);
    return;
  }

  if (deleting && charIndex > 0) {
    charIndex -= 1;
    setTimeout(tickTyping, 16);
    return;
  }

  deleting = false;
  promptIndex = (promptIndex + 1) % prompts.length;
  setTimeout(tickTyping, 260);
}

tickTyping();
