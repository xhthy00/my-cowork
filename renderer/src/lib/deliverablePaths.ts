import { artifactIdentity, decodeUnicodeEscapes, fileBasename } from './fsPath';
import { isProcessCodePath, isVisibleAgentPath } from './outputFiles';
import { resolveLocalFileLinkPath } from '@/components/chat/markdown/markdownUtils';
import type { FileArtifact, Message } from '@/store/session';
import { groupTurns } from '@/components/chat/groupTurns';

const EXT = '(?:html?|docx?|pptx?|xlsx?|pdf|md|txt|csv|tsv|json|zip|png|jpe?g|webp|gif|svg|bmp|mp3|wav|mp4|webm)';

/** Only candidates; the desktop host must verify existence before adding cards. */
export function referencedDeliverables(text: string): string[] {
  const body = decodeUnicodeEscapes(text);
  const absolute = new RegExp('(?:^|[\\s`\'"(<：:])((?:file:///|/|~/|[A-Za-z]:[\\\\/])[^\\r\\n`\'"<>|]*?\\.' + EXT + ')(?=$|[\\s`\'"<>),，。;；\\]])', 'gim');
  const paths = [...body.matchAll(absolute)].map(match => match[1]);
  const links = /\]\(<?([^\r\n]+?)>?\)(?=\s|$)/gm;
  paths.push(...[...body.matchAll(links)].map(match => match[1]));
  const seen = new Set<string>();
  return paths.flatMap(raw => {
    const path = resolveLocalFileLinkPath(raw);
    if (!path || !new RegExp('\\.' + EXT + '$', 'i').test(path) || !isVisibleAgentPath(path) || isProcessCodePath(path)) return [];
    const key = artifactIdentity(path);
    if (seen.has(key)) return [];
    seen.add(key);
    return [path];
  });
}

export function artifactForPath(path: string): FileArtifact {
  const ext = fileBasename(path).split('.').pop()?.toLowerCase();
  const kind = ext === 'docx' || ext === 'pptx' || ext === 'xlsx' || ext === 'pdf' ? ext : 'file';
  return { path, name: fileBasename(path), kind };
}

/** Restore missing cards in saved conversations, scoped to each turn's final answer. */
export async function recoverReferencedArtifacts(messages: Message[], verify: (paths: string[]) => Promise<string[]>): Promise<Map<string, FileArtifact[]>> {
  const candidates = groupTurns(messages).flatMap(turn => {
    if (turn.assistants.some(message => message.artifacts?.length)) return [];
    const final = [...turn.assistants].reverse().find(message => !message.confirm && !message.humanQuestion && !message.memoryNotice && message.content.trim());
    return final ? [{ message: final, paths: referencedDeliverables(final.content) }] : [];
  }).filter(item => item.paths.length);
  const paths = [...new Set(candidates.flatMap(item => item.paths))];
  const verified: string[] = [];
  for (let i = 0; i < paths.length; i += 200) verified.push(...await verify(paths.slice(i, i + 200)));
  const byId = new Map(verified.map(path => [artifactIdentity(path), path]));
  const result = new Map<string, FileArtifact[]>();
  for (const { message, paths } of candidates) {
    const found = paths.flatMap(path => {
      const verifiedPath = byId.get(artifactIdentity(path));
      return verifiedPath ? [artifactForPath(verifiedPath)] : [];
    });
    if (found.length) result.set(message.id, found);
  }
  return result;
}
