import { motion } from "framer-motion";
import { Activity } from "lucide-react";

export function ScanningScreen() {
  return (
    <motion.div
      initial={{ opacity: 1 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="card"
      role="status"
      aria-live="polite"
      aria-label="Executing campaign — running state machine loopback and evaluating PII leakage"
      style={{
        overflow: 'hidden', 
        position: 'relative', 
        minHeight: '400px', 
        display: 'flex', 
        flexDirection: 'column', 
        alignItems: 'center', 
        justifyContent: 'center',
        background: 'rgba(0,0,0,0.4)'
      }}
    >
      <motion.div 
        animate={{ y: ["-100%", "200%"] }}
        transition={{ repeat: Infinity, duration: 2.5, ease: "linear" }}
        style={{
          position: 'absolute',
          top: 0, left: 0, right: 0, height: '40%',
          background: 'linear-gradient(to bottom, transparent, rgba(204, 255, 0, 0.05), rgba(204, 255, 0, 0.2))',
          borderBottom: '1px solid var(--accent-acid)',
          zIndex: 0,
          boxShadow: '0 10px 30px rgba(204, 255, 0, 0.2)'
        }}
      />
      
      <motion.div
        initial={{ scale: 0.95 }}
        animate={{ scale: 1 }}
        transition={{ delay: 0.2 }}
        style={{ position: 'relative', zIndex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '24px', color: 'var(--accent-acid)' }}
      >
        <motion.div 
          animate={{ rotate: 360 }} 
          transition={{ repeat: Infinity, duration: 4, ease: "linear" }}
        >
          <Activity size={48} strokeWidth={1} />
        </motion.div>
        
        <div style={{ textAlign: 'center' }}>
          <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '20px', textTransform: 'uppercase', letterSpacing: '0.15em', marginBottom: '8px', color: 'var(--text-pure)' }}>
            Executing Campaign
          </h2>
          <motion.div 
            animate={{ opacity: [0.4, 1, 0.4] }} 
            transition={{ repeat: Infinity, duration: 1.5 }}
            style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.1em' }}
          >
            Running state machine loopback &middot; Evaluating PII leakage
          </motion.div>
        </div>
      </motion.div>
      
      {/* Decorative Grid */}
      <div style={{
        position: 'absolute',
        inset: 0,
        backgroundImage: 'linear-gradient(var(--glass-border) 1px, transparent 1px), linear-gradient(90deg, var(--glass-border) 1px, transparent 1px)',
        backgroundSize: '40px 40px',
        opacity: 0.1,
        zIndex: 0
      }} />
    </motion.div>
  );
}
