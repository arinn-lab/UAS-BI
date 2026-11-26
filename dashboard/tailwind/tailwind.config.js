// Konfigurasi Tailwind CSS untuk komponen HTML di dashboard.
// Kompilasi ulang (perlu Node.js) dari folder proyek:
//   npx tailwindcss@3 -c dashboard/tailwind/tailwind.config.js -i dashboard/tailwind/input.css -o dashboard/static/tailwind.css --minify
module.exports = {
  content: { relative: true, files: ["../*.py"] },
  prefix: "tw-",          // supaya tidak bentrok dengan kelas bawaan Streamlit
  important: true,        // supaya menang dari gaya bawaan Streamlit
  corePlugins: { preflight: false },  // reset CSS Tailwind tidak dipakai agar tampilan Streamlit tidak rusak
  theme: {
    extend: {
      colors: {
        tinta: { DEFAULT: "#2B2340", lemah: "#5C5470" },
        garis: "#E6E1F0",
        lavender: { 50: "#FAF8FF", 100: "#F4F0FD", 200: "#E9E2FB" },
        ungu: { 300: "#C9BCF0", 500: "#7B61C9", 600: "#6A4FC0", 700: "#4B3596" },
        rose: { 50: "#FFF3F6", 200: "#F8CCD9", 700: "#B0204F" },
      },
      fontFamily: {
        judul: ["'Bricolage Grotesque'", "'Segoe UI'", "sans-serif"],
        badan: ["Figtree", "'Segoe UI'", "sans-serif"],
      },
      boxShadow: { kartu: "0 8px 24px -12px rgba(106, 79, 192, 0.35)" },
    },
  },
};
