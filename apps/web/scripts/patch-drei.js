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
    if (content.includes('currentRoot.unmount();') && !content.includes('setTimeout(() => {')) {
      content = content.replace(
        'currentRoot.unmount();',
        'setTimeout(() => { try { currentRoot.unmount(); } catch {} }, 0);'
      );
      fs.writeFileSync(htmlJsPath, content, 'utf8');
      console.log('Successfully patched @react-three/drei Html.js for React 18/19 safe unmount.');
    }
  }

  if (fs.existsSync(htmlCjsPath)) {
    let content = fs.readFileSync(htmlCjsPath, 'utf8');
    if (content.includes('e.unmount()') && !content.includes('setTimeout((()=>{try{e.unmount()}catch{}}),0)')) {
      content = content.replace(
        'e.unmount()',
        'setTimeout((()=>{try{e.unmount()}catch{}}),0)'
      );
      fs.writeFileSync(htmlCjsPath, content, 'utf8');
      console.log('Successfully patched @react-three/drei Html.cjs.js for React 18/19 safe unmount.');
    }
  }
} catch (err) {
  console.warn('Failed to patch @react-three/drei Html:', err);
}
