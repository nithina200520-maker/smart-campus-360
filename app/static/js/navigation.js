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

      // Phase 3: building/floor plan filter dims non-matching pins
      if ((mapFilter.building && node.building !== mapFilter.building) ||
          (mapFilter.floor && node.floor !== mapFilter.floor)) {
        ctx.globalAlpha = 0.18;
      }

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

  // PHASE 3: Full-screen campus map viewing
  document.getElementById('btnFullscreen')?.addEventListener('click', () => {
    const container = document.querySelector('.map-canvas-container');
    if (!document.fullscreenElement) {
      container.requestFullscreen().catch(() => {});
    } else {
      document.exitFullscreen();
    }
  });

  // PHASE 3: Building / floor filter (floor plans view)
  const mapFilter = { building: '', floor: '' };
  document.getElementById('filterBuilding')?.addEventListener('change', (e) => {
    mapFilter.building = e.target.value;
    renderMap();
  });
  document.getElementById('filterFloor')?.addEventListener('change', (e) => {
    mapFilter.floor = e.target.value;
    renderMap();
  });

  // PHASE 3: Uploaded digital floor plan viewer
  const fpState = { zoom: 1, panX: 0, panY: 0, dragging: false, sx: 0, sy: 0 };
  function applyFpTransform() {
    const img = document.getElementById('floorPlanImg');
    if (img) img.style.transform = `translate(${fpState.panX}px, ${fpState.panY}px) scale(${fpState.zoom})`;
  }
  document.getElementById('floorPlanSelect')?.addEventListener('change', (e) => {
    const url = e.target.value;
    const layer = document.getElementById('floorPlanLayer');
    const backBtn = document.getElementById('btnBackToCampusMap');
    if (!url) {
      layer.classList.add('d-none');
      backBtn.classList.add('d-none');
      return;
    }
    const title = e.target.options[e.target.selectedIndex].dataset.title || 'Floor Plan';
    document.getElementById('floorPlanTitle').innerText = title;
    document.getElementById('floorPlanImg').src = url;
    fpState.zoom = 1; fpState.panX = 0; fpState.panY = 0;
    applyFpTransform();
    layer.classList.remove('d-none');
    backBtn.classList.remove('d-none');
  });
  document.getElementById('btnBackToCampusMap')?.addEventListener('click', () => {
    document.getElementById('floorPlanLayer').classList.add('d-none');
    document.getElementById('btnBackToCampusMap').classList.add('d-none');
    const sel = document.getElementById('floorPlanSelect');
    if (sel) sel.value = '';
  });
  const fpLayer = document.getElementById('floorPlanLayer');
  if (fpLayer) {
    fpLayer.addEventListener('dblclick', () => { fpState.zoom = Math.min(fpState.zoom * 1.4, 6); applyFpTransform(); });
    fpLayer.addEventListener('wheel', (e) => {
      e.preventDefault();
      fpState.zoom = Math.min(Math.max(fpState.zoom * (e.deltaY < 0 ? 1.15 : 0.87), 0.6), 6);
      applyFpTransform();
    }, { passive: false });
    fpLayer.addEventListener('mousedown', (e) => {
      fpState.dragging = true; fpState.sx = e.clientX - fpState.panX; fpState.sy = e.clientY - fpState.panY;
    });
    fpLayer.addEventListener('mousemove', (e) => {
      if (!fpState.dragging) return;
      fpState.panX = e.clientX - fpState.sx; fpState.panY = e.clientY - fpState.sy;
      applyFpTransform();
    });
    fpLayer.addEventListener('mouseup', () => { fpState.dragging = false; });
    fpLayer.addEventListener('mouseleave', () => { fpState.dragging = false; });
  }

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
          document.getElementById('btnStartWalkthrough')?.classList.remove('d-none');

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
    document.getElementById('btnStartWalkthrough')?.classList.add('d-none');
    renderMap();
  });

  // ------------------------------------------------------------------
  // PHASE 3: STREET-VIEW STYLE PHOTO VIEWER
  // Zoom, drag-to-explore, double-click zoom, fullscreen, directional
  // arrows to connected photographs, prev/next movement, route walkthrough.
  // ------------------------------------------------------------------
  let svState = {
    node: null,
    connections: [],
    connIndex: 0,
    zoom: 1,
    panX: 0,
    panY: 0,
    dragging: false,
    dragStartX: 0,
    dragStartY: 0,
    walkthrough: null // {steps: [...path_nodes], index}
  };
  let svModalInstance = null;

  function applySvTransform() {
    const img = document.getElementById('svModalImg');
    if (img) {
      img.style.transform = `translate(${svState.panX}px, ${svState.panY}px) scale(${svState.zoom})`;
    }
  }

  function resetSvView() {
    svState.zoom = svState.node && svState.node.is_panoramic ? 1.6 : 1;
    svState.panX = 0;
    svState.panY = 0;
    applySvTransform();
  }

  function renderSvConnections() {
    const strip = document.getElementById('svConnections');
    if (!strip) return;
    if (!svState.connections.length) {
      strip.innerHTML = `<span class="small text-white-50 px-2"><i class="fa-solid fa-road me-1"></i>No mapped walkable connections from this point yet.</span>`;
      return;
    }
    strip.innerHTML = svState.connections.map((c, i) => `
      <button class="sv-arrow-btn" data-index="${i}" title="${c.direction_hint} (${c.distance_meters}m)">
        <i class="fa-solid fa-arrow-turn-up fa-rotate-90 me-1"></i>
        <span class="sv-arrow-label">${c.node.name.replace('[SAMPLE]', '').trim()}</span>
        <span class="sv-arrow-dist">${c.direction_hint ? c.direction_hint.split(' ')[0] : 'Go'} • ${c.distance_meters}m</span>
      </button>`).join('');

    strip.querySelectorAll('.sv-arrow-btn').forEach(btn => {
      btn.addEventListener('click', () => moveViewerToConnection(parseInt(btn.dataset.index)));
    });
  }

  function moveViewerToConnection(index) {
    const conn = svState.connections[index];
    if (!conn) return;
    svState.connIndex = index;
    loadViewerNode(conn.node, conn.direction_hint ? `${conn.direction_hint} — ${conn.distance_meters}m` : null);
  }

  function loadViewerNode(node, instruction) {
    svState.node = node;
    document.getElementById('svModalName').innerText = node.name;
    document.getElementById('svModalLocation').innerText = `${node.building} • ${node.floor}`;
    document.getElementById('svModalBadge').innerText = node.category;
    document.getElementById('svModalDesc').innerText = node.description || "Photographs of buildings, corridors, staircases and rooms.";
    document.getElementById('svModalImg').src = node.photo_url || "/static/images/placeholder_node.jpg";
    document.getElementById('svModalInstruction').innerText = instruction
      ? instruction
      : (svState.walkthrough
          ? `Walkthrough stop ${svState.walkthrough.index + 1} of ${svState.walkthrough.steps.length}: ${node.name}`
          : `You are at ${node.name}. Use the arrows below to move to a connected photograph.`);
    const panoBadge = document.getElementById('svModalPanoBadge');
    if (panoBadge) panoBadge.classList.toggle('d-none', !node.is_panoramic);
    resetSvView();

    fetch(`/navigation/api/node/${node.id}/connections`)
      .then(res => res.json())
      .then(data => {
        if (data.success) {
          svState.connections = data.connections;
          svState.connIndex = 0;
          renderSvConnections();
        }
      });
  }

  // Street View Modal Trigger (from map clicks)
  function openStreetViewModal(node) {
    svState.walkthrough = null;
    if (!svModalInstance) {
      svModalInstance = new bootstrap.Modal(document.getElementById('streetViewModal'));
    }
    svModalInstance.show();
    loadViewerNode(node, null);
  }

  // Photo viewer interaction: dblclick zoom, drag explore, wheel zoom
  const svViewport = document.getElementById('svViewport');
  if (svViewport) {
    svViewport.addEventListener('dblclick', (e) => {
      if (e.target.closest('.sv-control-bar') || e.target.closest('.sv-connections-strip')) return;
      svState.zoom = Math.min(svState.zoom * 1.4, 6);
      applySvTransform();
    });
    svViewport.addEventListener('wheel', (e) => {
      e.preventDefault();
      svState.zoom = Math.min(Math.max(svState.zoom * (e.deltaY < 0 ? 1.15 : 0.87), 0.6), 6);
      applySvTransform();
    }, { passive: false });
    svViewport.addEventListener('mousedown', (e) => {
      if (e.target.closest('button')) return;
      svState.dragging = true;
      svState.dragStartX = e.clientX - svState.panX;
      svState.dragStartY = e.clientY - svState.panY;
      svViewport.classList.add('sv-grabbing');
    });
    window.addEventListener('mousemove', (e) => {
      if (!svState.dragging) return;
      svState.panX = e.clientX - svState.dragStartX;
      svState.panY = e.clientY - svState.dragStartY;
      applySvTransform();
    });
    window.addEventListener('mouseup', () => {
      svState.dragging = false;
      svViewport.classList.remove('sv-grabbing');
    });
  }

  document.getElementById('svZoomIn')?.addEventListener('click', () => { svState.zoom = Math.min(svState.zoom * 1.25, 6); applySvTransform(); });
  document.getElementById('svZoomOut')?.addEventListener('click', () => { svState.zoom = Math.max(svState.zoom * 0.8, 0.6); applySvTransform(); });
  document.getElementById('svResetZoom')?.addEventListener('click', resetSvView);
  document.getElementById('svFullscreen')?.addEventListener('click', () => {
    const modalBox = document.querySelector('#streetViewModal .modal-content');
    if (!document.fullscreenElement) {
      modalBox.requestFullscreen().catch(() => {});
    } else {
      document.exitFullscreen();
    }
  });
  document.getElementById('svPrevPhoto')?.addEventListener('click', () => {
    if (svState.walkthrough) return walkthroughStep(-1);
    if (svState.connections.length) moveViewerToConnection((svState.connIndex - 1 + svState.connections.length) % svState.connections.length);
  });
  document.getElementById('svNextPhoto')?.addEventListener('click', () => {
    if (svState.walkthrough) return walkthroughStep(1);
    if (svState.connections.length) moveViewerToConnection((svState.connIndex + 1) % svState.connections.length);
  });

  // Route walkthrough: photo associated with each navigation point
  function walkthroughStep(delta) {
    if (!svState.walkthrough) return;
    const steps = svState.walkthrough.steps;
    let next = svState.walkthrough.index + delta;
    if (next < 0) next = 0;
    if (next > steps.length - 1) next = steps.length - 1;
    svState.walkthrough.index = next;
    const stepNode = steps[next];
    const instr = next < steps.length - 1 && activeInstructions[next]
      ? `${activeInstructions[next].instruction} (${activeInstructions[next].distance_meters}m)`
      : 'Arrival: you have reached the destination of this route.';
    loadViewerNode(stepNode, `Stop ${next + 1}/${steps.length} — ${instr}`);
  }

  document.getElementById('btnStartWalkthrough')?.addEventListener('click', function () {
    if (!activePathNodes.length) return;
    svState.walkthrough = { steps: activePathNodes, index: 0 };
    openStreetViewModal(activePathNodes[0]);
    document.getElementById('svModalInstruction').innerText =
      `Walkthrough started — ${activePathNodes.length} photo stops. Use ▶ to follow the route.`;
  });

  // Global helper for directory list cards (id based)
  window.selectAndFocusNode = function (id) {
    fetch(`/navigation/api/node/${id}`)
      .then(res => res.json())
      .then(data => {
        if (data.success) openStreetViewModal(data.node);
      });
  };

  // Directory card click delegation
  document.querySelectorAll('.node-item').forEach(el => {
    el.addEventListener('click', () => window.selectAndFocusNode(parseInt(el.dataset.id)));
  });

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
