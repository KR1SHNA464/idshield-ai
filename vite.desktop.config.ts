import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/postcss';
import path from 'node:path';
export default defineConfig({root:'.',plugins:[react()],resolve:{alias:{'@':path.resolve(import.meta.dirname,'.')}},css:{postcss:{plugins:[tailwindcss()]}},build:{outDir:'desktop-dist',emptyOutDir:true,rollupOptions:{input:'desktop/index.html'}},publicDir:'public'});
