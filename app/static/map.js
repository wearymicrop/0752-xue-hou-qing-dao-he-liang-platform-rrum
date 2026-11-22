const colors = {covered:'#21816a', pending:'#b56b31', unknown:'#7089a0'};

export function draw(canvas, roads, selected, jobs = []) {
  const width = canvas.clientWidth, height = canvas.clientHeight, ratio = devicePixelRatio || 1;
  if (!width || !height) return;
  canvas.width = width * ratio; canvas.height = height * ratio;
  const ctx = canvas.getContext('2d'); ctx.scale(ratio, ratio);
  ctx.fillStyle = '#eef5f9'; ctx.fillRect(0, 0, width, height);
  for (let step = 0; step < width + height; step += 24) {
    stroke([[step, 0], [step, height]], '#d9e8f0', 1);
    stroke([[0, step], [width, step]], '#d9e8f0', 1);
  }
  const xs = roads.flatMap(row => [row.axis[0], row.axis[2]]);
  const ys = roads.flatMap(row => [row.axis[1], row.axis[3]]);
  if (!xs.length) return;
  const xMin = Math.min(...xs), xMax = Math.max(...xs), yMin = Math.min(...ys), yMax = Math.max(...ys);
  const sx = (width - 64) / Math.max(1, xMax - xMin), sy = (height - 82) / Math.max(1, yMax - yMin);
  const xy = (row, m) => {
    const [x0,y0,x1,y1] = row.axis, fraction = m / row.length_m;
    const offset = row.direction === '-' && roads.some(item => item.road === row.road && item.direction === '+') ? 11 : 0;
    return [30 + (x0 + (x1 - x0) * fraction - xMin) * sx, 43 + (yMax - y0 - (y1-y0)*fraction) * sy + offset];
  };
  function stroke(points, color, thickness) {
    ctx.beginPath(); ctx.moveTo(...points[0]); points.slice(1).forEach(point => ctx.lineTo(...point));
    ctx.strokeStyle = color; ctx.lineWidth = thickness; ctx.stroke();
  }
  for (const row of roads) {
    const active = selected === `${row.road}/${row.direction}`;
    const bounds = [xy(row, row.from_m), xy(row, row.to_m)];
    stroke(bounds, active ? '#173a57' : '#b8cad8', active ? 14 : 11);
    for (const part of row.parts) {
      ctx.setLineDash(part.kind === 'unknown' ? [8,3] : []);
      stroke([xy(row,part.from_m), xy(row,part.to_m)], colors[part.kind], active ? 8 : 6);
      ctx.setLineDash([]);
    }
    for (const point of bounds) {
      ctx.beginPath(); ctx.arc(...point, 3, 0, 2 * Math.PI); ctx.fillStyle = '#f9fcff'; ctx.fill();
    }
    if (row.direction === '-' && roads.some(item => item.road === row.road && item.direction === '+')) continue;
    const [x,y] = xy(row, (row.from_m + row.to_m) / 2);
    ctx.font = `${active ? 'bold ' : ''}12px sans-serif`;
    ctx.lineWidth = 5; ctx.strokeStyle = '#f2f8fb'; ctx.strokeText(row.name, x - 23, y - 13);
    ctx.fillStyle = '#223f57'; ctx.fillText(row.name, x - 23, y - 13);
  }
  if (!jobs.length) return;
  // Dispatch overlay: each vehicle in its own colour, hop number at the entry,
  // a dashed line for the transfer drive between two stitched gaps.
  const palette = ['#23587f','#9c3d4f','#5a6f1f','#7a4b9c','#b06d16','#1d6f74','#8b2f6b'];
  const byVehicle = new Map();
  for (const job of jobs) {
    if (!job.task_id) continue;
    byVehicle.set(job.vehicle, [...(byVehicle.get(job.vehicle) ?? []), job]);
  }
  let index = 0;
  for (const [vehicle, stops] of byVehicle) {
    const colour = palette[index++ % palette.length];
    let previous = null;
    for (const stop of stops) {
      const row = roads.find(item => item.road === stop.road && item.direction === stop.direction);
      if (!row) continue;
      const points = [xy(row, stop.entry_m), xy(row, stop.exit_m)];
      if (previous) {
        ctx.setLineDash([4,4]); ctx.globalAlpha = .65;
        stroke([previous, points[0]], colour, 2);
        ctx.globalAlpha = 1; ctx.setLineDash([]);
      }
      stroke(points, colour, 5);
      if (stops.length > 1) {
        ctx.beginPath(); ctx.arc(...points[0], 8, 0, 2 * Math.PI);
        ctx.fillStyle = colour; ctx.fill();
        ctx.fillStyle = '#fff'; ctx.font = 'bold 10px sans-serif'; ctx.textAlign = 'center';
        ctx.fillText(String(stop.seq), points[0][0], points[0][1] + 3.5);
        ctx.textAlign = 'start';
      }
      previous = points[1];
    }
  }
}
