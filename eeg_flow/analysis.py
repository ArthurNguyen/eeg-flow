"""ERP analysis."""

import mne
import numpy as np
from autoreject import get_rejection_threshold

from . import logger
from .utils._docs import fill_doc
from .utils._checks import _check_type


@fill_doc
def erp(raw, bandpass, ref_channels, copy=False):
    """
    Apply simple ERP processing to raw instance.
        - Picks EEG, EOG, ECG channels
        - Bandpass FIR filter on EEG
        - Bandpass FIR filter on AUX
        - Notch (50, 100) Hz on AUX
        - Set EEG reference.
        - Fit ICA, plot scores for EOG/ECG component correlation and plot
          sources to interactively exclude them
        - Create epochs around audio stimulus (-0.2, 0.5), apply baseline
          correction from the first 200 ms
        - Compute peak-to-peak rejection threshold and apply rejection
        - Create evoked response

    Parameters
    ----------
    %(raw)s
    bandpass : tuple
        2-length tuple (l_freq, h_freq) used to BP filter the EEG signal.
        e.g. (1., 45.) or (1., 15.)
    ref_channels : list of str | str
        Can be:
            - The name(s) of the channel(s) used to construct the reference.
              e.g. ['M1', 'M2']
            - 'average' to apply a CAR reference.
    copy : bool
        If True, operates on a copy of the raw instance.

    Returns
    -------
    evoked_standard : mne.Evoked
        Evoked response for the standard sound stimulus.
    evoked_target : mne.Evoked
        Evoked response for the target sound stimulus.
    evoked_novel : mne.Evoked
        Evoked response for the novel sound stimulus.
    """
    _check_type(raw, (mne.io.BaseRaw, ), item_name='raw')
    _check_type(bandpass, (bool, list), item_name='bandpass')
    assert len(bandpass) == 2
    for fq in bandpass:
        _check_type(fq, (None, 'numeric'))
    _check_type(copy, (bool, ), item_name='copy')

    raw = raw.copy() if copy else raw
    raw.pick_types(stim=True, eeg=True, eog=True, ecg=True)

    # bandpass filter
    raw.filter(
        l_freq=bandpass[0],
        h_freq=bandpass[1],
        picks='eeg',
        method="fir",
        phase="zero-double",
        fir_window="hamming",
        fir_design="firwin",
        pad="edge")

    # bandpass filter + notch on aux
    raw.filter(
        l_freq=1.,
        h_freq=45.,
        picks=['eog', 'ecg'],
        method="fir",
        phase="zero-double",
        fir_window="hamming",
        fir_design="firwin",
        pad="edge")
    raw.notch_filter(np.arange(50, 101, 50), picks=['eog', 'ecg'])

    # Reference
    raw.set_eeg_reference(ref_channels=ref_channels, projection=False,
                          ch_type='eeg')

    # ICA
    ica = mne.preprocessing.ICA(method='picard', max_iter='auto')
    ica.fit(raw, picks='eeg')
    eog_idx, eog_scores = ica.find_bads_eog(
        raw, threshold=0.5, measure='correlation')
    logger.info('Proposed occular-related components: %s', eog_idx)
    ecg_idx, ecg_scores = ica.find_bads_ecg(
        raw, method='correlation', threshold=0.6, measure='correlation')
    logger.info('Proposed heartbeat-related components: %s', ecg_idx)
    ica.plot_scores(eog_scores)
    ica.plot_scores(ecg_scores)
    ica.plot_sources(raw, block=True)  # exclude bad components
    logger.info('Components excluded: %s', ica.exclude)
    ica.apply(raw)

    # Create Epochs
    events = mne.find_events(raw, stim_channel='TRIGGER')
    events_id = dict(standard=1, target=2, novel=3)
    epochs = mne.Epochs(raw, events, events_id, tmin=-0.2, tmax=0.5,
                        baseline=(None, 0), reject=None, picks='eeg',
                        preload=True)
    reject = get_rejection_threshold(epochs, decim=1)
    logger.info('Peak-to-peak rejection threshold computed: %s', reject)
    epochs.drop_bad(reject=reject)
    epochs.plot_drop_log()

    # Create Evoked
    evoked_standard = epochs['standard'].average()
    evoked_target = epochs['target'].average()
    evoked_novel = epochs['novel'].average()

    return evoked_standard, evoked_target, evoked_novel