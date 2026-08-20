(function () {
    const theme = localStorage.getItem('theme') || 'dark';
    document.documentElement.setAttribute('data-theme', theme);

    // Run this on DOMContentLoaded to ensure body etc are available
    document.addEventListener('DOMContentLoaded', () => {
        const savedTheme = localStorage.getItem('theme') || 'dark';
        document.documentElement.setAttribute('data-theme', savedTheme);
    });

    window.setTheme = function (t) {
        document.documentElement.setAttribute('data-theme', t);
        localStorage.setItem('theme', t);
        console.log('Theme set to:', t);
    };
})();
