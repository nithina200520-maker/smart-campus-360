/**
 * SMART CAMPUS 360 - INTERACTIVE CAMPUS MAP & NAVIGATION ENGINE
 * Government Engineering College, Mosalehosahalli (Hassan)
 */

document.addEventListener('DOMContentLoaded', function () {
  const canvas = document.getElementById('campusMapCanvas');
  if (!canvas) return;

  const ctx = canvas.getContext('2d');
  let nodes = [];
  let activePathNodes = [];
  let activeInstructions = [];

  // Canvas Viewport Transformation State
  let scale = 1.0;
  let offsetX = 0;
  let offsetY = 0;
  let isDragging = false;
  let startDragX = 0;
  let startDragY = 0;

  // Node Category Visual Styles
  const CATEGORY_COLORS = {
    'Gate': '#64748b',
    'Office': '#7c3aed',
    'Laboratory': '#2563eb',
    'Classroom': '#0284c7',
    'Library': '#d97706',
    'Canteen': '#dc2626',
    'Sports Ground': '#16a34a',
    'Auditorium': '#9333ea',
    'Corridor': '#94a3b8'
  };

  // Fetch nodes from API
  fetch('/navigation/api/nodes')
    .then(res => res.json())
    .then(data => {
      if (data.success) {
        nodes = data.nodes;
        renderMap();
      }
    })
    .catch(err => console.error("Error loading nodes:", err));

  // Render Map Canvas
  function renderMap() {
    ctx.save();
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Apply translation and zoom
    ctx.translate(offsetX, offsetY);
    ctx.scale(scale, scale);

    // 1. Draw Campus Grounds & Base Geography
    drawCampusEnvironment();

    // 2. Draw Connecting Pathway Grid
    drawPathwayNetwork();

    // 3. Draw Active Route with Pulsing Glow & Directional Arrows
    if (activePathNodes.length > 1) {
      drawActiveRoute();
    }

    // 4. Draw Navigation Nodes & Location Pins
    drawNodes();

    ctx.restore();
  }

  // Draw stylized campus layout representing GEC Mosalehosahalli campus grounds
  function drawCampusEnvironment() {
    // Base grass lawn
    ctx.fillStyle = "#e2e8f0";
    ctx.fillRect(0, 0, 1000, 650);

    // Campus green parks & quadrangle gardens
    ctx.fillStyle = "#dcfce7";
    ctx.beginPath();
    ctx.roundRect(140, 140, 720, 360, 24);
    ctx.fill();

    // Central garden quadrangle
    ctx.fillStyle = "#bbf7d0";
    ctx.beginPath();
    ctx.roundRect(320, 260, 320, 180, 16);
    ctx.fill();

    // Main entrance boulevard
    ctx.fillStyle = "#cbd5e1";
    ctx.fillRect(40, 340, 220, 40);

    // Connecting avenues
    ctx.fillStyle = "#cbd5e1";
    // East-West central road
    ctx.fillRect(220, 340, 560, 40);
    // North Academic Road
    ctx.fillRect(220, 200, 560, 30);
    // South Technical Avenue
    ctx.fillRect(220, 480, 560, 30);
    // Connecting vertical avenues
    ctx.fillRect(210, 200, 30, 310);
    ctx.fillRect(390, 200, 30, 310);
    ctx.fillRect(550, 200, 30, 310);
    ctx.fillRect(690, 200, 30, 310);

    // Building Footprints (Blocks)
    drawBuildingBlock(180, 210, 80, 60, "Admin Block", "#f8fafc", "#64748b");
    drawBuildingBlock(360, 170, 90, 70, "Block A (CSE)", "#eff6ff", "#3b82f6");
    drawBuildingBlock(360, 450, 90, 70, "Block B (ECE)", "#eff6ff", "#3b82f6");
    drawBuildingBlock(520, 150, 90, 70, "Central Lib", "#fffbeb", "#f59e0b");
    drawBuildingBlock(520, 480, 90, 70, "Mech Block", "#f1f5f9", "#475569");
    drawBuildingBlock(660, 320, 90, 80, "Canteen", "#fef2f2", "#ef4444");
    drawBuildingBlock(660, 160, 90, 60, "Seminar Hall", "#faf5ff", "#8b5cf6");
    drawBuildingBlock(790, 430, 120, 90, "Sports Field", "#ecfdf5", "#10b981");
  }

  function drawBuildingBlock(x, y, w, h, title, fill, stroke) {
    ctx.save();
    ctx.fillStyle = fill;
    ctx.strokeStyle = stroke;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.roundRect(x, y, w, h, 8);
    ctx.fill();
    ctx.stroke();

    ctx.fillStyle = "#334155";
    ctx.font = "bold 11px system-ui";
    ctx.textAlign = "center";
    ctx.fillText(title, x + w / 2, y + h / 2 + 4);
    ctx.restore();
  }

  // Draw subtle connecting pathways
  function drawPathwayNetwork() {
    ctx.strokeStyle = "#94a3b8";
    ctx.lineWidth = 2;
    ctx.setLineDash([4, 4]);

    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const dx = nodes[i].x_coord - nodes[j].x_coord;
        const dy = nodes[i].y_coord - nodes[j].y_coord;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < 260) {
          ctx.beginPath();
          ctx.moveTo(nodes[i].x_coord, nodes[i].y_coord);
          ctx.lineTo(nodes[j].x_coord, nodes[j].y_coord);
          ctx.stroke();
        }
      }
    }
    ctx.setLineDash([]);
  }

  // Draw active route path with directional arrows
  function drawActiveRoute() {
    if (activePathNodes.length < 2) return;

    ctx.save();
    // Glowing shadow for route
    ctx.shadowColor = "rgba(37, 99, 235, 0.6)";
    ctx.shadowBlur = 12;

    // Route line
    ctx.strokeStyle = "#2563eb";
    ctx.lineWidth = 5;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";

    ctx.beginPath();
    ctx.moveTo(activePathNodes[0].x, activePathNodes[0].y);
    for (let i = 1; i < activePathNodes.length; i++) {
      ctx.lineTo(activePathNodes[i].x, activePathNodes[i].y);
    }
    ctx.stroke();
    ctx.restore();

    // Draw directional arrows along segments
    for (let i = 0; i < activePathNodes.length - 1; i++) {
      const p1 = activePathNodes[i];
      const p2 = activePathNodes[i + 1];
      const midX = (p1.x + p2.x) / 2;
      const midY = (p1.y + p2.y) / 2;
      const angle = Math.atan2(p2.y - p1.y, p2.x - p1.x);

      drawArrowHead(midX, midY, angle, "#1d4ed8");
    }
  }

  function drawArrowHead(x, y, angle, color) {
    ctx.save();
    ctx.translate(x, y);
    ctx.rotate(angle);
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.moveTo(0, 0);
    ctx.lineTo(-10, -5);
    ctx.lineTo(-6, 0);
    ctx.lineTo(-10, 5);
    ctx.closePath();
    ctx.fill();
    ctx.restore();
  }

  // Draw node pins and labels
  function drawNodes() {
    nodes.forEach(node => {
      const color = CATEGORY_COLORS[node.category] || "#2563eb";
      const isStart = activePathNodes.length > 0 && activePathNodes[0].id === node.id;
      const isTarget = activePathNodes.length > 1 && activePathNodes[activePathNodes.length - 1].id === node.id;

      ctx.save();

      // Outer ring for route endpoints
      if (isStart) {
        ctx.strokeStyle = "#16a34a";
        ctx.lineWidth = 4;
        ctx.beginPath();
        ctx.arc(node.x_coord, node.y_coord, 16, 0, Math.PI * 2);
        ctx.stroke();
      } else if (isTarget) {
        ctx.strokeStyle = "#dc2626";
        ctx.lineWidth = 4;
        ctx.beginPath();
        ctx.arc(node.x_coord, node.y_coord, 16, 0, Math.PI * 2);
        ctx.stroke();
      }

      // Node Pin Body
      ctx.fillStyle = isStart ? "#16a34a" : (isTarget ? "#dc2626" : color);
      ctx.beginPath();
      ctx.arc(node.x_coord, node.y_coord, 9, 0, Math.PI * 2);
      ctx.fill();

      // White center dot
      ctx.fillStyle = "#ffffff";
      ctx.beginPath();
      ctx.arc(node.x_coord, node.y_coord, 3.5, 0, Math.PI * 2);
      ctx.fill();

      // Text label with backdrop for legibility
      const label = node.name.replace('[SAMPLE]', '').trim();
      ctx.font = "bold 10px system-ui";
      ctx.textAlign = "center";

      const textWidth = ctx.measureText(label).width;
      ctx.fillStyle = "rgba(255, 255, 255, 0.85)";
      ctx.fillRect(node.x_coord - textWidth / 2 - 3, node.y_coord - 22, textWidth + 6, 12);

      ctx.fillStyle = "#0f172a";
      ctx.fillText(label, node.x_coord, node.y_coord - 13);

      ctx.restore();
    });
  }

  // Double-Click Zoom at Mouse Cursor Position
  canvas.addEventListener('dblclick', function (e) {
    const rect = canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    // Check if clicked directly on a node for street view
    const canvasX = (mouseX - offsetX) / scale;
    const canvasY = (mouseY - offsetY) / scale;

    const clickedNode = findNodeAt(canvasX, canvasY);
    if (clickedNode) {
      openStreetViewModal(clickedNode);
      return;
    }

    // Otherwise zoom in centered on mouse
    const zoomFactor = 1.35;
    offsetX = mouseX - (mouseX - offsetX) * zoomFactor;
    offsetY = mouseY - (mouseY - offsetY) * zoomFactor;
    scale *= zoomFactor;
    renderMap();
  });

  // Single Click to open Street View if node is clicked
  canvas.addEventListener('click', function (e) {
    const rect = canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    const canvasX = (mouseX - offsetX) / scale;
    const canvasY = (mouseY - offsetY) / scale;

    const clickedNode = findNodeAt(canvasX, canvasY);
    if (clickedNode) {
      openStreetViewModal(clickedNode);
    }
  });

  function findNodeAt(x, y) {
    return nodes.find(n => {
      const dx = n.x_coord - x;
      const dy = n.y_coord - y;
      return Math.sqrt(dx * dx + dy * dy) <= 15;
    });
  }

  // Pan Canvas Interaction
  canvas.addEventListener('mousedown', function (e) {
    isDragging = true;
    startDragX = e.clientX - offsetX;
    startDragY = e.clientY - offsetY;
  });

  window.addEventListener('mousemove', function (e) {
    if (!isDragging) return;
    offsetX = e.clientX - startDragX;
    offsetY = e.clientY - startDragY;
    renderMap();
  });

  window.addEventListener('mouseup', function () {
    isDragging = false;
  });

  // Mouse Wheel Zoom
  canvas.addEventListener('wheel', function (e) {
    e.preventDefault();
    const rect = canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    const zoomFactor = e.deltaY < 0 ? 1.15 : 0.88;
    const newScale = Math.min(Math.max(scale * zoomFactor, 0.5), 3.5);

    offsetX = mouseX - (mouseX - offsetX) * (newScale / scale);
    offsetY = mouseY - (mouseY - offsetY) * (newScale / scale);
    scale = newScale;

    renderMap();
  }, { passive: false });

  // Map Controls (Buttons)
  document.getElementById('btnZoomIn')?.addEventListener('click', () => {
    scale = Math.min(scale * 1.25, 3.5);
    renderMap();
  });

  document.getElementById('btnZoomOut')?.addEventListener('click', () => {
    scale = Math.max(scale * 0.8, 0.5);
    renderMap();
  });

  document.getElementById('btnResetView')?.addEventListener('click', () => {
    scale = 1.0;
    offsetX = 0;
    offsetY = 0;
    renderMap();
  });

  // Calculate Route Button Trigger
  document.getElementById('btnFindRoute')?.addEventListener('click', function () {
    const startId = document.getElementById('startNodeSelect').value;
    const targetId = document.getElementById('targetNodeSelect').value;
    const algo = document.querySelector('input[name="algoRadio"]:checked')?.value || 'astar';

    if (!startId || !targetId) {
      alert("Please select both a Start Location and a Destination.");
      return;
    }

    if (startId === targetId) {
      alert("Start location and destination cannot be the same.");
      return;
    }

    fetch('/navigation/api/route', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        start_node_id: parseInt(startId),
        target_node_id: parseInt(targetId),
        algorithm: algo
      })
    })
    .then(res => res.json())
    .then(data => {
      if (data.success) {
        activePathNodes = data.path_nodes;
        activeInstructions = data.instructions;

        // Update Route Badge
        const summaryBadge = document.getElementById('routeSummaryBadge');
        const statsText = document.getElementById('routeStatsText');
        if (summaryBadge && statsText) {
          summaryBadge.classList.remove('d-none');
          statsText.innerHTML = `<i class="fa-solid fa-person-walking me-1"></i> ${data.total_distance_meters} meters • Approx. ${data.estimated_time_minutes} min walk (${data.algorithm})`;
        }

        // Populate Directions List
        const dirCard = document.getElementById('directionsCard');
        const dirList = document.getElementById('directionsList');
        const algoBadge = document.getElementById('activeAlgorithmBadge');

        if (dirCard && dirList) {
          dirCard.classList.remove('d-none');
          algoBadge.innerText = `${data.algorithm} OPTIMAL PATH`;

          dirList.innerHTML = data.instructions.map((step, idx) => `
            <div class="direction-step-card d-flex justify-content-between align-items-center">
              <div>
                <span class="badge bg-primary me-2">Step ${idx + 1}</span>
                <span class="fw-bold text-dark">${step.instruction}</span>
                <div class="small text-muted mt-1">
                  <i class="fa-solid fa-arrow-right-long text-secondary me-1"></i> Distance: ${step.distance_meters}m
                </div>
              </div>
              <button class="btn btn-sm btn-outline-primary rounded-pill" onclick="previewStepPOI('${step.to_node}')">
                <i class="fa-solid fa-camera"></i> POV
              </button>
            </div>
          `).join('');
        }

        renderMap();
      } else {
        alert(data.error || "No route could be found.");
      }
    })
    .catch(err => console.error("Route calculation error:", err));
  });

  // Reset Route
  document.getElementById('btnClearRoute')?.addEventListener('click', function () {
    activePathNodes = [];
    activeInstructions = [];
    document.getElementById('routeSummaryBadge')?.classList.add('d-none');
    document.getElementById('directionsCard')?.classList.add('d-none');
    renderMap();
  });

  // Street View Modal Trigger
  function openStreetViewModal(node) {
    document.getElementById('svModalName').innerText = node.name;
    document.getElementById('svModalLocation').innerText = `${node.building} • ${node.floor}`;
    document.getElementById('svModalBadge').innerText = node.category;
    document.getElementById('svModalDesc').innerText = node.description || "Real college photographs can be imported without code changes.";
    document.getElementById('svModalImg').src = node.photo_url || "/static/images/placeholder_node.jpg";

    const modal = new bootstrap.Modal(document.getElementById('streetViewModal'));
    modal.show();
  }

  // Global helper for step buttons and directory list
  window.selectAndFocusNode = function (id, name, x, y, photo, building, floor, desc) {
    document.getElementById('targetNodeSelect').value = id;
    openStreetViewModal({
      id: id,
      name: name,
      building: building,
      floor: floor,
      category: 'Location POI',
      description: desc,
      photo_url: photo
    });
  };

  window.previewStepPOI = function (nodeName) {
    const targetNode = nodes.find(n => n.name === nodeName || n.name.includes(nodeName));
    if (targetNode) {
      openStreetViewModal(targetNode);
    }
  };

  // Instant Search Filter
  document.getElementById('nodeSearchInput')?.addEventListener('input', function (e) {
    const q = e.target.value.toLowerCase().trim();
    document.querySelectorAll('.node-item').forEach(el => {
      const name = el.getAttribute('data-name').toLowerCase();
      const cat = el.getAttribute('data-category').toLowerCase();
      const bld = el.getAttribute('data-building').toLowerCase();
      if (name.includes(q) || cat.includes(q) || bld.includes(q)) {
        el.style.display = 'block';
      } else {
        el.style.display = 'none';
      }
    });
  });

});
