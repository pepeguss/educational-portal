module.exports = {
  content: {
    relative: true,
    files: ['../templates/**/*.html', '../player/templates/**/*.html', '../users/templates/**/*.html', '../static/js/*.js'],
  },
  theme: {
    extend: {
      colors: {
        graphite: { 50: '#f6f7f8', 100: '#e6e8eb', 500: '#3a3f47', 700: '#2a2e35', 900: '#1a1d23' },
        amber: { 500: '#f5b301', 600: '#d99c00' },
      },
      fontFamily: { sans: ['Inter', 'system-ui', 'sans-serif'] },
    },
  },
};
