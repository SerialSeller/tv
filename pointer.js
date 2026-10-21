// Low-vision pointer: a 128px yellow arrow as the page cursor, plus a big ring that follows the pointer.
// The TV browser may draw its own small pointer and ignore the CSS cursor; the ring works either way,
// because the page still receives mousemove events.
(function () {
  var css = '* { cursor: url(media/cursor.png) 8 5, auto !important; }' +
    '#pointerRing { position: fixed; left: 0; top: 0; width: 120px; height: 120px; margin: -60px 0 0 -60px;' +
    ' border: 8px solid #ffd400; border-radius: 50%; box-shadow: 0 0 0 4px #000, inset 0 0 0 4px #000;' +
    ' pointer-events: none; z-index: 9999; display: none; }';
  var style = document.createElement('style');
  style.appendChild(document.createTextNode(css));
  document.getElementsByTagName('head')[0].appendChild(style);

  var ring = document.createElement('div');
  ring.id = 'pointerRing';
  document.body.appendChild(ring);

  var idle = null;
  function move(e) {
    e = e || window.event;
    ring.style.left = e.clientX + 'px';
    ring.style.top = e.clientY + 'px';
    ring.style.display = 'block';
    if (idle) { clearTimeout(idle); }
    idle = setTimeout(function () { ring.style.display = 'none'; }, 4000);
  }
  // Listen alongside the pages' own handlers instead of replacing document.onmousemove.
  if (document.addEventListener) { document.addEventListener('mousemove', move, false); }
})();
