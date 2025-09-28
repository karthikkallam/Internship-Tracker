import React from 'react';
import { Job } from '../types';

interface JobCardProps {
  job: Job;
}

const formatPostedAt = (postedAt?: string | null) => {
  if (!postedAt) {
    return 'Posted date unavailable';
  }
  const dt = new Date(postedAt);
  if (Number.isNaN(dt.getTime())) {
    return 'Posted date unavailable';
  }
  const now = Date.now();
  const diffMs = dt.getTime() - now;
  const diffMinutes = Math.round(diffMs / (60 * 1000));
  const formatter = new Intl.RelativeTimeFormat('en', { numeric: 'auto' });

  if (Math.abs(diffMinutes) < 60) {
    return formatter.format(Math.round(diffMinutes), 'minute');
  }
  const diffHours = Math.round(diffMinutes / 60);
  if (Math.abs(diffHours) < 24) {
    return formatter.format(diffHours, 'hour');
  }
  const diffDays = Math.round(diffHours / 24);
  return formatter.format(diffDays, 'day');
};

export function JobCard({ job }: JobCardProps) {
  return (
    <article className="group flex flex-col justify-between rounded-xl border border-slate-800 bg-slate-900/70 p-5 shadow-lg transition hover:-translate-y-1 hover:border-brand-500/50 hover:shadow-brand-500/20">
      <div className="flex flex-col gap-2">
        <span className="text-xs uppercase tracking-wide text-brand-300">{job.source}</span>
        <h3 className="text-xl font-semibold text-slate-50 group-hover:text-brand-300">
          {job.title}
        </h3>
        <p className="text-sm text-slate-400">
          {job.company}
          {job.location ? ` • ${job.location}` : ''}
        </p>
        <p className="text-xs text-slate-500">{formatPostedAt(job.posted_at)}</p>
      </div>
      <div className="mt-4 flex items-center justify-between">
        <span className="text-xs font-medium uppercase tracking-widest text-brand-300">
          Apply directly
        </span>
        <a
          href={job.url}
          className="inline-flex items-center gap-2 rounded-full bg-brand-500 px-4 py-2 text-sm font-semibold text-white transition hover:bg-brand-400"
          target="_blank"
          rel="noopener noreferrer"
        >
          Apply →
        </a>
      </div>
    </article>
  );
}

export default JobCard;
