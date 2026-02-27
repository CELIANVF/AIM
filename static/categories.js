// categories.js - handle drag & drop reordering
(function(){
    function init(){
        console.log('categories drag script loaded');
        window.addEventListener('error', function(e){
            console.error('JS error in categories drag script', e.error, e.message);
        });
        const grid = document.querySelector('.grid');
        if(!grid) { console.log('no grid element found'); return; }
        console.log('grid items count', grid.querySelectorAll('.item').length);
        let dragSrc = null;

        function sendOrder(){
            const order = Array.from(grid.querySelectorAll('.item')).map(i=>i.dataset.id);
            fetch('/reorder_categories',{
                method: 'POST',
                credentials: 'same-origin',
                headers: {'Content-Type':'application/json','X-Requested-With':'XMLHttpRequest'},
                body: JSON.stringify({order: order})
            }).then(r=>{
                if(!r.ok) console.error('Reorder failed');
                else {
                    // brief visual feedback on container
                    grid.classList.add('order-saved');
                    setTimeout(()=>grid.classList.remove('order-saved'), 300);
                }
            }).catch(err=>console.error('Network error', err));
        }

        // allow dropping anywhere on the grid
        grid.addEventListener('dragover', function(e){ e.preventDefault(); }); // allow drop anywhere

        // start drag from handle for better cross-browser behaviour
        grid.querySelectorAll('.drag-handle').forEach(handle=>{
            handle.addEventListener('dragstart', function(e){
                console.log('handle dragstart');
                dragSrc = this.closest('.item');
                if(!dragSrc) return;
                dragSrc.classList.add('dragging');
                try{ e.dataTransfer.setData('text/plain', dragSrc.dataset.id); }catch(_){ }
                e.dataTransfer.effectAllowed = 'move';
            });
            handle.addEventListener('dragend', function(){
                if(dragSrc) dragSrc.classList.remove('dragging');
                grid.querySelectorAll('.item').forEach(i=>i.classList.remove('drag-over-top','drag-over-bottom'));
                dragSrc = null;
            });
        });

        // also allow dragging by grabbing the whole item (fallback)
        grid.querySelectorAll('.item').forEach(item=>{
            item.addEventListener('dragstart', function(e){
                console.log('item dragstart', this.dataset.id);
                dragSrc = this;
                dragSrc.classList.add('dragging');
                try{ e.dataTransfer.setData('text/plain', dragSrc.dataset.id); }catch(_){ }
                e.dataTransfer.effectAllowed = 'move';
            });
            item.addEventListener('dragend', function(){
                if(dragSrc) dragSrc.classList.remove('dragging');
                grid.querySelectorAll('.item').forEach(i=>i.classList.remove('drag-over-top','drag-over-bottom'));
                dragSrc = null;
            });
        });

        grid.querySelectorAll('.item').forEach(item=>{
            item.addEventListener('dragover', function(e){
                e.preventDefault();
                e.dataTransfer.dropEffect = 'move';
                if(this === dragSrc) return;
                const rect = this.getBoundingClientRect();
                const offset = e.clientY - rect.top;
                if(offset < rect.height/2){
                    this.classList.add('drag-over-top'); this.classList.remove('drag-over-bottom');
                } else {
                    this.classList.add('drag-over-bottom'); this.classList.remove('drag-over-top');
                }
            });
            item.addEventListener('dragleave', function(){
                this.classList.remove('drag-over-top','drag-over-bottom');
            });
            item.addEventListener('drop', function(e){
                console.log('drop on', this.dataset.id);
                e.preventDefault();
                if(!dragSrc || this === dragSrc) return;
                // swap DOM nodes dragSrc <-> this
                const a = dragSrc;
                const b = this;
                const parent = a.parentNode;
                const aNext = a.nextSibling;
                parent.replaceChild(a, b);
                if(aNext === b){
                    parent.insertBefore(b, a);
                } else {
                    parent.insertBefore(b, aNext);
                }
                parent.querySelectorAll('.item').forEach(i=>i.classList.remove('drag-over-top','drag-over-bottom'));
                sendOrder();
            });
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
