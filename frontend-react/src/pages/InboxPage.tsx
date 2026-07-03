import { useState, useEffect } from 'react';
import { Mail, Reply, Send, Search, RefreshCw, X as XIcon, Loader, Sparkles } from 'lucide-react';
import { api } from '../api';
import { useToast } from '../components/Toast';
import Modal from '../components/Modal';
import { PageHeader, Button, EmptyState, LoadingState } from '../components/ui';
import { filterFieldClass } from '../components/styles';
import DOMPurify from 'dompurify';

interface Email {
  id: string;
  from_addr: string;
  to_addr: string;
  subject: string;
  date: string;
  snippet: string;
  is_read: boolean;
  has_attachments: boolean;
}

interface EmailDetail {
  id: string;
  from_addr: string;
  to_addr: string;
  subject: string;
  date: string;
  body_html: string | null;
  body_text: string | null;
  is_read: boolean;
  attachments: Array<{ filename: string; content_type: string; size: number }>;
}

export default function InboxPage() {
  const { toast } = useToast();
  const [emails, setEmails] = useState<Email[]>([]);
  const [selectedEmail, setSelectedEmail] = useState<EmailDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [unreadOnly, setUnreadOnly] = useState(false);
  
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [mobileShowDetail, setMobileShowDetail] = useState(false);
  
  // Reply state
  const [showReply, setShowReply] = useState(false);
  const [replyBody, setReplyBody] = useState('');
  const [replying, setReplying] = useState(false);
  
  // Scan replies
  const [scanning, setScanning] = useState(false);
  const [scanResult, setScanResult] = useState<any>(null);

  // Compose state
  const [composeOpen, setComposeOpen] = useState(false);
  const [composeTo, setComposeTo] = useState('');
  const [composeSubject, setComposeSubject] = useState('');
  const [composeBody, setComposeBody] = useState('');
  const [composing, setComposing] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => loadEmails(), search ? 400 : 0);
    return () => clearTimeout(t);
  }, [search, unreadOnly]);

  // SSE stream for real-time new email notifications
  useEffect(() => {
    const token = localStorage.getItem('token');
    const es = new EventSource(`/api/v1/inbox/stream?token=${token}`);
    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'new_email' && data.new > 0) {
          loadEmails();
          toast(`${data.new} new email${data.new > 1 ? 's' : ''}`, 'success');
        }
      } catch {}
    };
    return () => es.close();
  }, []);

  async function loadEmails() {
    try {
      setLoading(true);
      const data = await api.getEmails(100, 0, unreadOnly, search);
      setEmails(data);
    } catch (e: any) {
      toast(e.message, 'error');
    } finally {
      setLoading(false);
    }
  }

  async function selectEmail(email: Email) {
    setSelectedId(email.id);
    try {
      setDetailLoading(true);
      const detail = await api.getEmail(email.id);
      setSelectedEmail(detail);
      setShowReply(false);
      setReplyBody('');
      setMobileShowDetail(true);
      
      // Mark as read if unread
      if (!detail.is_read) {
        await api.markEmailRead(email.id);
        // Update local state
        setEmails(prev => prev.map(e => e.id === email.id ? { ...e, is_read: true } : e));
      }
    } catch (e: any) {
      toast(e.message, 'error');
    } finally {
      setDetailLoading(false);
    }
  }

  async function handleReply() {
    if (!selectedEmail || !replyBody.trim()) return;
    
    try {
      setReplying(true);
      await api.replyToEmail(selectedEmail.id, replyBody, true);
      toast('Reply sent!', 'success');
      setShowReply(false);
      setReplyBody('');
      loadEmails();
    } catch (e: any) {
      toast(e.message, 'error');
    } finally {
      setReplying(false);
    }
  }

  async function handleScanReplies() {
    setScanning(true);
    setScanResult(null);
    try {
      const r = await api.scanReplies();
      setScanResult(r);
      if (r.processed > 0) {
        toast(`Parsed ${r.processed} replies — check domain pages for extracted data`, 'success');
        loadEmails();
      } else {
        toast('No new replies to process', 'success');
      }
    } catch (e: any) { toast(e.message || 'Scan failed', 'error'); }
    setScanning(false);
  }

  async function handleCompose() {
    if (!composeTo.trim() || !composeSubject.trim() || !composeBody.trim()) {
      toast('Please fill in all fields', 'error');
      return;
    }
    
    try {
      setComposing(true);
      await api.composeEmail(composeTo, composeSubject, composeBody);
      toast('Email sent!', 'success');
      setComposeOpen(false);
      setComposeTo('');
      setComposeSubject('');
      setComposeBody('');
    } catch (e: any) {
      toast(e.message, 'error');
    } finally {
      setComposing(false);
    }
  }

  function formatDate(dateStr: string) {
    try {
      const date = new Date(dateStr);
      const now = new Date();
      const diff = now.getTime() - date.getTime();
      const days = Math.floor(diff / (1000 * 60 * 60 * 24));
      
      if (days === 0) {
        return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
      } else if (days < 7) {
        return date.toLocaleDateString('en-US', { weekday: 'short' });
      } else {
        return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
      }
    } catch {
      return dateStr;
    }
  }

  function renderEmailBody(email: EmailDetail) {
    const body = email.body_html || email.body_text || '';
    
    if (email.body_html) {
      // Sanitize HTML
      const clean = DOMPurify.sanitize(body, {
        ALLOWED_TAGS: ['p', 'br', 'strong', 'em', 'u', 'a', 'ul', 'ol', 'li', 'blockquote', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'div', 'span', 'img'],
        ALLOWED_ATTR: ['href', 'src', 'alt', 'title', 'style', 'class'],
      });
      return <div dangerouslySetInnerHTML={{ __html: clean }} className="prose prose-invert max-w-none" />;
    } else {
      return <pre className="whitespace-pre-wrap font-sans text-sm text-gray-300">{body}</pre>;
    }
  }

  return (
    <div className="min-h-[calc(100vh-8rem)]">
      {/* Header */}
      <div className="mb-6">
        <PageHeader
          title="Inbox"
          description={`${emails.filter(e => !e.is_read).length} unread`}
          actions={<>
            <button
              onClick={handleScanReplies}
              disabled={scanning}
              className="inline-flex items-center justify-center gap-1.5 px-4 py-2 text-sm rounded-lg bg-gray-700 hover:bg-gray-600 transition-colors disabled:opacity-50 disabled:pointer-events-none"
              title="Scan unread replies and extract contact info, prices, and payment methods using AI"
            >
              <Sparkles className={`w-4 h-4 ${scanning ? 'animate-pulse' : ''}`} />
              <span className="hidden sm:inline">{scanning ? 'Scanning...' : 'Scan Replies'}</span>
              <span className="sm:hidden">{scanning ? 'Scan...' : 'Scan'}</span>
            </button>
            <Button onClick={() => setComposeOpen(true)} aria-label="Compose email" variant="primary" icon={Send}>
              <span className="hidden sm:inline">Compose</span>
            </Button>
            <Button onClick={loadEmails} variant="ghost" title="Refresh" aria-label="Refresh inbox">
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </Button>
          </>}
        />
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3 sm:gap-4 mb-4">
        <div className="relative flex-1 sm:max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
          <input
            type="text"
            placeholder="Search emails..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className={`${filterFieldClass} w-full pl-10`}
          />
        </div>
        
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={unreadOnly}
            onChange={(e) => setUnreadOnly(e.target.checked)}
            className="w-4 h-4 text-pink-600 bg-gray-800 border-gray-700 rounded focus:ring-pink-500"
          />
          <span className="text-sm text-gray-300">Unread only</span>
        </label>
      </div>

      {/* Scan Results */}
      {scanResult && scanResult.processed > 0 && (
        <div className="p-4 bg-gray-800 border border-gray-700 rounded-lg">
          <div className="text-sm font-medium mb-2">Parsed {scanResult.processed} replies:</div>
          <div className="space-y-1">
            {scanResult.results.map((r: any, i: number) => (
              <div key={i} className="text-xs text-gray-300">
                <span className="text-teal-400 font-medium">{r.domain}</span>
                {r.error ? (
                  <span className="text-red-400 ml-2">Error: {r.error}</span>
                ) : (
                  <span className="text-gray-400 ml-2">{r.actions?.join(', ')}</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Split Layout */}
      <div className="flex flex-col lg:flex-row gap-4 min-h-[500px] lg:h-[calc(100vh-20rem)]">
        {/* Email List */}
        <div className={`w-full lg:w-1/3 bg-gray-800 rounded-lg border border-gray-700 overflow-hidden flex flex-col lg:max-h-none ${mobileShowDetail ? 'hidden lg:flex' : 'flex min-h-[400px]'}`}>
          <div className="flex-1 overflow-y-auto">
            {loading ? (
              <LoadingState label="Loading emails..." className="h-full" />
            ) : emails.length === 0 ? (
              <div className="flex items-center justify-center h-full">
                <EmptyState icon={Mail} title="No emails found" />
              </div>
            ) : (
              <div className="divide-y divide-gray-700">
                {emails.map((email) => (
                  <div
                    key={email.id}
                    onClick={() => selectEmail(email)}
                    className={`p-4 cursor-pointer transition-colors ${
                      selectedId === email.id ? 'bg-pink-600/15 ring-1 ring-pink-500/30' : 'hover:bg-gray-700/50'
                    } ${!email.is_read ? 'border-l-2 border-pink-500' : ''}`}
                  >
                    <div className="flex items-start justify-between gap-2 mb-1">
                      <div className="font-mono text-[13px] font-medium truncate flex-1">
                        {email.from_addr}
                      </div>
                      <div className="text-xs text-gray-500 shrink-0">
                        {formatDate(email.date)}
                      </div>
                    </div>
                    <div className={`text-sm mb-1 truncate ${!email.is_read ? 'font-semibold' : 'text-gray-400'}`}>
                      {email.subject}
                    </div>
                    <div className="text-xs text-gray-500 line-clamp-2">
                      {email.snippet}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Email Detail */}
        <div className={`flex-1 bg-gray-800 rounded-lg border border-gray-700 overflow-hidden flex flex-col ${!mobileShowDetail ? 'hidden lg:flex' : 'flex'}`}>
          {detailLoading ? (
            <LoadingState label="Loading email..." className="h-full" />
          ) : !selectedEmail ? (
            <div className="flex items-center justify-center h-full text-gray-500">
              <div className="text-center">
                <Mail className="w-12 h-12 mx-auto mb-2 text-gray-600" />
                <div>Select an email to view</div>
              </div>
            </div>
          ) : (
            <>
              {/* Email Header */}
              <div className="p-4 sm:p-6 border-b border-gray-700 shrink-0">
                <button
                  onClick={() => setMobileShowDetail(false)}
                  className="lg:hidden mb-3 text-sm text-gray-400 hover:text-white flex items-center gap-1"
                >
                  ← Back to inbox
                </button>
                <h2 className="text-lg sm:text-xl font-semibold mb-4">{selectedEmail.subject}</h2>
                
                <div className="space-y-2 text-sm">
                  <div className="flex items-start gap-2">
                    <span className="text-gray-500 w-16 shrink-0">From:</span>
                    <span className="font-mono text-[13px] text-gray-300">{selectedEmail.from_addr}</span>
                  </div>
                  <div className="flex items-start gap-2">
                    <span className="text-gray-500 w-16 shrink-0">To:</span>
                    <span className="font-mono text-[13px] text-gray-300">{selectedEmail.to_addr}</span>
                  </div>
                  <div className="flex items-start gap-2">
                    <span className="text-gray-500 w-16 shrink-0">Date:</span>
                    <span className="text-gray-300">{new Date(selectedEmail.date).toLocaleString()}</span>
                  </div>
                  {selectedEmail.attachments.length > 0 && (
                    <div className="flex items-start gap-2">
                      <span className="text-gray-500 w-16 shrink-0">Attachments:</span>
                      <div className="flex flex-wrap gap-2">
                        {selectedEmail.attachments.map((att, idx) => (
                          <span key={idx} className="text-xs bg-gray-700 px-2 py-1 rounded">
                            {att.filename} ({(att.size / 1024).toFixed(1)}KB)
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>

                <div className="mt-4 flex gap-2">
                  <Button onClick={() => setShowReply(!showReply)} variant="primary" icon={Reply}>
                    Reply
                  </Button>
                </div>
              </div>

              {/* Email Body */}
              <div className="flex-1 overflow-y-auto p-4 sm:p-6">
                {renderEmailBody(selectedEmail)}
              </div>

              {/* Reply Form */}
              {showReply && (
                <div className="p-4 sm:p-6 border-t border-gray-700 bg-gray-900 shrink-0">
                  <div className="mb-3 flex items-center justify-between">
                    <span className="text-sm font-medium">Reply to {selectedEmail.from_addr}</span>
                    <button
                      onClick={() => setShowReply(false)}
                      className="text-gray-500 hover:text-gray-300"
                      aria-label="Close reply"
                    >
                      <XIcon className="w-4 h-4" />
                    </button>
                  </div>
                  
                  <textarea
                    value={replyBody}
                    onChange={(e) => setReplyBody(e.target.value)}
                    placeholder="Type your reply..."
                    rows={6}
                    className="w-full bg-gray-800 border border-gray-700 rounded-lg p-3 focus:ring-2 focus:ring-pink-500 focus:border-transparent resize-none"
                  />
                  
                  <div className="mt-3 flex justify-end gap-2">
                    <Button onClick={() => setShowReply(false)}>Cancel</Button>
                    <Button onClick={handleReply} disabled={replying || !replyBody.trim()} variant="primary">
                      {replying ? (
                        <>
                          <Loader className="w-4 h-4 animate-spin" />
                          Sending...
                        </>
                      ) : (
                        <>
                          <Send className="w-4 h-4" />
                          Send Reply
                        </>
                      )}
                    </Button>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* Compose Modal */}
      <Modal open={composeOpen} onClose={() => setComposeOpen(false)} title="Compose Email">
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">To</label>
            <input
              type="email"
              value={composeTo}
              onChange={(e) => setComposeTo(e.target.value)}
              placeholder="recipient@example.com"
              className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 focus:ring-2 focus:ring-pink-500 focus:border-transparent"
            />
          </div>
          
          <div>
            <label className="block text-sm font-medium mb-1">Subject</label>
            <input
              type="text"
              value={composeSubject}
              onChange={(e) => setComposeSubject(e.target.value)}
              placeholder="Email subject"
              className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 focus:ring-2 focus:ring-pink-500 focus:border-transparent"
            />
          </div>
          
          <div>
            <label className="block text-sm font-medium mb-1">Message</label>
            <textarea
              value={composeBody}
              onChange={(e) => setComposeBody(e.target.value)}
              placeholder="Type your message..."
              rows={10}
              className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 focus:ring-2 focus:ring-pink-500 focus:border-transparent resize-none"
            />
          </div>
          
          <div className="flex justify-end gap-2 pt-2">
            <Button onClick={() => setComposeOpen(false)}>Cancel</Button>
            <Button
              onClick={handleCompose}
              disabled={composing || !composeTo.trim() || !composeSubject.trim() || !composeBody.trim()}
              variant="primary"
            >
              {composing ? (
                <>
                  <Loader className="w-4 h-4 animate-spin" />
                  Sending...
                </>
              ) : (
                <>
                  <Send className="w-4 h-4" />
                  Send Email
                </>
              )}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
