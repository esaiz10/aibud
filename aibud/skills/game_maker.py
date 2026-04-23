from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path


def build_arcade_skill(runtime, project_name: str, prompt: str) -> dict:
    slug = datetime.now(UTC).strftime("asteroids_%Y%m%d_%H%M%S")
    out_dir = Path(runtime.projects_dir) / slug
    runtime.tools.write_file(
        str(out_dir / "index.html"),
        """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Asteroids-ish</title>
    <link rel="stylesheet" href="./styles.css">
  </head>
  <body>
    <canvas id="game" width="960" height="540"></canvas>
    <script src="./game.js"></script>
  </body>
</html>
""",
    )
    runtime.tools.write_file(
        str(out_dir / "styles.css"),
        """html, body {
  margin: 0;
  height: 100%;
  background: radial-gradient(circle at top, #17325c, #05070d 65%);
  overflow: hidden;
}

canvas {
  display: block;
  margin: 0 auto;
  width: min(100vw, 960px);
  height: min(100vh, 540px);
}
""",
    )
    runtime.tools.write_file(
        str(out_dir / "game.js"),
        """const canvas = document.getElementById("game");
const ctx = canvas.getContext("2d");
const keys = new Set();
const ship = { x: 480, y: 270, angle: 0, vx: 0, vy: 0, r: 18 };
const bullets = [];
const rocks = Array.from({ length: 7 }, () => ({
  x: Math.random() * canvas.width,
  y: Math.random() * canvas.height,
  vx: (Math.random() - 0.5) * 2,
  vy: (Math.random() - 0.5) * 2,
  r: 22 + Math.random() * 30,
}));

addEventListener("keydown", (event) => keys.add(event.key));
addEventListener("keyup", (event) => keys.delete(event.key));
addEventListener("keypress", (event) => {
  if (event.code === "Space") {
    bullets.push({
      x: ship.x,
      y: ship.y,
      vx: Math.cos(ship.angle) * 7,
      vy: Math.sin(ship.angle) * 7,
      ttl: 90,
    });
  }
});

function wrap(body) {
  body.x = (body.x + canvas.width) % canvas.width;
  body.y = (body.y + canvas.height) % canvas.height;
}

function tick() {
  if (keys.has("ArrowLeft")) ship.angle -= 0.07;
  if (keys.has("ArrowRight")) ship.angle += 0.07;
  if (keys.has("ArrowUp")) {
    ship.vx += Math.cos(ship.angle) * 0.09;
    ship.vy += Math.sin(ship.angle) * 0.09;
  }

  ship.x += ship.vx;
  ship.y += ship.vy;
  ship.vx *= 0.995;
  ship.vy *= 0.995;
  wrap(ship);

  bullets.forEach((bullet) => {
    bullet.x += bullet.vx;
    bullet.y += bullet.vy;
    bullet.ttl -= 1;
    wrap(bullet);
  });
  for (let i = bullets.length - 1; i >= 0; i -= 1) {
    if (bullets[i].ttl <= 0) bullets.splice(i, 1);
  }

  rocks.forEach((rock) => {
    rock.x += rock.vx;
    rock.y += rock.vy;
    wrap(rock);
  });

  for (let i = rocks.length - 1; i >= 0; i -= 1) {
    const rock = rocks[i];
    for (let j = bullets.length - 1; j >= 0; j -= 1) {
      const bullet = bullets[j];
      const dx = rock.x - bullet.x;
      const dy = rock.y - bullet.y;
      if (Math.hypot(dx, dy) < rock.r) {
        rocks.splice(i, 1);
        bullets.splice(j, 1);
        break;
      }
    }
  }

  draw();
  requestAnimationFrame(tick);
}

function draw() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  drawStars();
  drawShip();
  drawBullets();
  drawRocks();
  ctx.fillStyle = "#d7e6ff";
  ctx.font = "18px monospace";
  ctx.fillText(`Rocks left: ${rocks.length}`, 18, 28);
}

function drawStars() {
  for (let i = 0; i < 60; i += 1) {
    ctx.fillStyle = i % 9 === 0 ? "#ffffff" : "#7aa2ff";
    ctx.fillRect((i * 173) % canvas.width, (i * 97) % canvas.height, 2, 2);
  }
}

function drawShip() {
  ctx.save();
  ctx.translate(ship.x, ship.y);
  ctx.rotate(ship.angle);
  ctx.strokeStyle = "#fff2b2";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(24, 0);
  ctx.lineTo(-14, -12);
  ctx.lineTo(-8, 0);
  ctx.lineTo(-14, 12);
  ctx.closePath();
  ctx.stroke();
  ctx.restore();
}

function drawBullets() {
  ctx.fillStyle = "#ffd166";
  bullets.forEach((bullet) => {
    ctx.beginPath();
    ctx.arc(bullet.x, bullet.y, 3, 0, Math.PI * 2);
    ctx.fill();
  });
}

function drawRocks() {
  ctx.strokeStyle = "#9cc7ff";
  ctx.lineWidth = 2;
  rocks.forEach((rock) => {
    ctx.beginPath();
    for (let i = 0; i < 8; i += 1) {
      const angle = (Math.PI * 2 * i) / 8;
      const radius = rock.r + Math.sin(i * 1.7) * 8;
      const x = rock.x + Math.cos(angle) * radius;
      const y = rock.y + Math.sin(angle) * radius;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.closePath();
    ctx.stroke();
  });
}

tick();
""",
    )
    task = runtime.storage.create_task(
        runtime.ensure_project(project_name)["id"],
        "Playtest generated asteroid game",
        details=f"Open {out_dir / 'index.html'} in a browser and tune controls if needed.",
        status="queued",
        priority=2,
    )
    report = runtime.storage.add_report(
        "Arcade skill output",
        f"Generated a browser game scaffold at {out_dir}. Prompt: {prompt}",
    )
    runtime.storage.add_memory(
        "artifact",
        "Arcade build",
        f"Created Asteroids-inspired prototype in {out_dir}.",
    )
    return {
        "summary": "Generated an Asteroids-inspired browser game.",
        "response": (
            f"I generated a playable Asteroids-style prototype in `{out_dir}` "
            f"with `index.html`, `styles.css`, and `game.js`."
        ),
        "task_id": task["id"],
        "report_id": report["id"],
        "artifacts": [str(out_dir / "index.html"), str(out_dir / "game.js"), str(out_dir / "styles.css")],
    }
