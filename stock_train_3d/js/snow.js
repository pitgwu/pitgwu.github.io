// js/snow.js
// 雪花效果
(function () {
  function createSnowflake() {
    const snow = document.createElement("div");
    snow.className = "snowflake";
    snow.style.left = Math.random() * window.innerWidth + "px";
    const size = Math.random() * 8 + 4;
    snow.style.width = size + "px";
    snow.style.height = size + "px";
    snow.style.opacity = Math.random();
    document.body.appendChild(snow);

    const fallDuration = Math.random() * 5000 + 5000;
    const startLeft = parseFloat(snow.style.left);
    let startTime = null;

    function animate(timestamp) {
      if (!startTime) startTime = timestamp;
      const progress = timestamp - startTime;
      const fraction = progress / fallDuration;
      snow.style.top = fraction * window.innerHeight + "px";
      snow.style.left = startLeft + Math.sin(fraction * Math.PI * 2) * 50 + "px";
      if (fraction < 1) requestAnimationFrame(animate);
      else snow.remove();
    }
    requestAnimationFrame(animate);
  }

  setInterval(createSnowflake, 200);
})();
