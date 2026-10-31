import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const htmlJsPath = path.resolve(__dirname, '../node_modules/@react-three/drei/web/Html.js');
const htmlCjsPath = path.resolve(__dirname, '../node_modules/@react-three/drei/web/Html.cjs.js');

try {
  if (fs.existsSync(htmlJsPath)) {
    let content = fs.readFileSync(htmlJsPath, 'utf8');

    // 1. Prevent duplicate createRoot calls on the same container element
    content = content.replace(
      'const currentRoot = root.current = ReactDOM.createRoot(el);',
      'const currentRoot = root.current || (root.current = ReactDOM.createRoot(el));'
    );

    // 2. Safe removeChild check to prevent "node to be removed is not a child of this node"
    content = content.replace(
      'if (target) target.removeChild(el);',
      'if (target && target.contains(el)) { try { target.removeChild(el); } catch {} }'
    );

    // 3. Remove unmount from the [target, transform] layout effect
    const searchLayoutCleanup = `      return () => {
        if (target && target.contains(el)) { try { target.removeChild(el); } catch {} }
        setTimeout(() => {
          try {
            currentRoot.unmount();
          } catch {
            // Root already unmounted
          }
        }, 0);
      };`;
    const cleanLayoutCleanup = `      return () => {
        if (target && target.contains(el)) { try { target.removeChild(el); } catch {} }
      };`;
    if (content.includes(searchLayoutCleanup)) {
      content = content.replace(searchLayoutCleanup, cleanLayoutCleanup);
    }

    // Also match unpatched version if applicable
    const unpatchedCleanup = `      return () => {
        if (target) target.removeChild(el);
        currentRoot.unmount();
      };`;
    if (content.includes(unpatchedCleanup)) {
      content = content.replace(unpatchedCleanup, cleanLayoutCleanup);
    }

    // 4. Safely unmount root only on component teardown
    if (!content.includes('/* safe-html-unmount */')) {
      content = content.replace(
        'React.useLayoutEffect(() => {\n    if (wrapperClass) el.className = wrapperClass;\n  }, [wrapperClass]);',
        `/* safe-html-unmount */
  React.useEffect(() => {
    return () => {
      if (root.current) {
        const r = root.current;
        root.current = null;
        setTimeout(() => {
          try {
            r.unmount();
          } catch {}
        }, 0);
      }
    };
  }, []);
  React.useLayoutEffect(() => {
    if (wrapperClass) el.className = wrapperClass;
  }, [wrapperClass]);`
      );
    }

    fs.writeFileSync(htmlJsPath, content, 'utf8');
    console.log('Successfully patched @react-three/drei Html.js for React 18/19 safe root & removeChild.');
  }

  if (fs.existsSync(htmlCjsPath)) {
    let content = fs.readFileSync(htmlCjsPath, 'utf8');

    // 1. Prevent duplicate createRoot in CJS
    content = content.replace(
      'const e=G.current=l.createRoot(D);',
      'const e=G.current||(G.current=l.createRoot(D));'
    );

    // 2. Safe removeChild & prevent premature unmount in CJS
    content = content.replace(
      'U&&U.removeChild(D),setTimeout((()=>{try{e.unmount()}catch{}}),0)',
      'U&&U.contains(D)&&U.removeChild(D)'
    );
    content = content.replace(
      'U&&U.removeChild(D),e.unmount()',
      'U&&U.contains(D)&&U.removeChild(D)'
    );

    // 3. Unmount on component teardown in CJS
    if (!content.includes('/* safe-html-unmount */')) {
      content = content.replace(
        'c.useLayoutEffect((()=>{k&&(D.className=k)}),[k])',
        '/* safe-html-unmount */c.useEffect((()=>()=>{if(G.current){const e=G.current;G.current=null;setTimeout((()=>{try{e.unmount()}catch{}}),0)}}),[]),c.useLayoutEffect((()=>{k&&(D.className=k)}),[k])'
      );
      content = content.replace(
        'c.useLayoutEffect((()=>{C&&(D.className=C)}),[C])',
        '/* safe-html-unmount */c.useEffect((()=>()=>{if(G.current){const e=G.current;G.current=null;setTimeout((()=>{try{e.unmount()}catch{}}),0)}}),[]),c.useLayoutEffect((()=>{C&&(D.className=C)}),[C])'
      );
    }

    fs.writeFileSync(htmlCjsPath, content, 'utf8');
    console.log('Successfully patched @react-three/drei Html.cjs.js for React 18/19 safe root & removeChild.');
  }
} catch (err) {
  console.warn('Failed to patch @react-three/drei Html:', err);
}
